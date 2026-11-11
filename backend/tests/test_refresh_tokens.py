"""Refresh-token lifecycle: rotation, replay detection, expiry and revocation."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import RefreshToken

PASSWORD = "supersecret123"
EMAIL = "refresh@example.com"


def register(client: TestClient, email: str = EMAIL) -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> dict:
    response = client.post(
        "/api/v1/auth/access-token", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def refresh(client: TestClient, token: str) -> tuple[int, dict]:
    response = client.post("/api/v1/auth/refresh-token", json={"refresh_token": token})
    body = response.json()
    return response.status_code, body.get("data", body)


def me(client: TestClient, access_token: str) -> int:
    return client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
    ).status_code


def latest_row(session: Session) -> RefreshToken:
    """Newest refresh-token row. `id` is UUIDv7, so it sorts by creation time."""
    row = session.exec(select(RefreshToken).order_by(RefreshToken.id.desc())).first()  # type: ignore[attr-defined]
    assert row is not None
    return row


# ---------------------------------------------------------------------------
# Login response
# ---------------------------------------------------------------------------
def test_login_returns_a_token_pair(client: TestClient) -> None:
    register(client)
    body = login(client)

    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    # Access and refresh tokens are distinct credentials.
    assert body["access_token"] != body["refresh_token"]
    assert body["expires_in"] > 0


def test_refresh_issues_a_working_access_token(client: TestClient) -> None:
    register(client)
    first = login(client)

    status, rotated = refresh(client, first["refresh_token"])
    assert status == 200, rotated
    assert me(client, rotated["access_token"]) == 200


# ---------------------------------------------------------------------------
# Rotation and replay detection
# ---------------------------------------------------------------------------
def test_refresh_rotates_the_token(client: TestClient) -> None:
    register(client)
    first = login(client)

    _, rotated = refresh(client, first["refresh_token"])
    assert rotated["refresh_token"] != first["refresh_token"]


def test_refresh_token_is_never_stored_in_plaintext(client: TestClient, session: Session) -> None:
    register(client)
    tokens = login(client)

    stored = session.exec(select(RefreshToken)).all()
    assert stored, "expected a refresh token row"
    assert all(row.token_hash != tokens["refresh_token"] for row in stored)


def test_reusing_a_rotated_token_revokes_the_whole_chain(client: TestClient) -> None:
    register(client)
    first = login(client)
    _, second = refresh(client, first["refresh_token"])

    # Replaying the consumed token looks like a stolen copy.
    assert refresh(client, first["refresh_token"])[0] == 401

    # ...so the chain is killed, including the newest token.
    assert refresh(client, second["refresh_token"])[0] == 401


def test_replay_does_not_affect_other_sessions(client: TestClient) -> None:
    register(client)
    device_a = login(client)
    device_b = login(client)

    _, rotated_a = refresh(client, device_a["refresh_token"])
    assert refresh(client, device_a["refresh_token"])[0] == 401

    # Device B holds a different family and must still work.
    assert refresh(client, device_b["refresh_token"])[0] == 200
    # The newest token from device A's chain is dead too.
    assert refresh(client, rotated_a["refresh_token"])[0] == 401


# ---------------------------------------------------------------------------
# Expiry (the idle window)
# ---------------------------------------------------------------------------
def test_expired_refresh_token_is_rejected(client: TestClient, session: Session) -> None:
    register(client)
    tokens = login(client)

    row = latest_row(session)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(row)
    session.commit()

    assert refresh(client, tokens["refresh_token"])[0] == 401


def test_refresh_extends_the_idle_window(client: TestClient, session: Session) -> None:
    register(client)
    first = login(client)

    # Shrink the window on the live row, then refresh.
    row = latest_row(session)
    row.expires_at = datetime.now(UTC) + timedelta(minutes=1)
    session.add(row)
    session.commit()

    status, _ = refresh(client, first["refresh_token"])
    assert status == 200

    # The replacement lives far beyond the old window: activity slides it.
    assert latest_row(session).expires_at > datetime.now(UTC) + timedelta(days=1)


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------
def test_logout_revokes_the_session(client: TestClient) -> None:
    register(client)
    tokens = login(client)

    response = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert refresh(client, tokens["refresh_token"])[0] == 401


def test_logout_is_idempotent_for_unknown_tokens(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 200


def test_password_change_revokes_refresh_tokens(client: TestClient) -> None:
    register(client)
    tokens = login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    changed = client.patch(
        "/api/v1/users/me", json={"password": "a-brand-new-password"}, headers=headers
    )
    assert changed.status_code == 200

    assert refresh(client, tokens["refresh_token"])[0] == 401
    # A fresh login works and yields a usable pair.
    fresh = login(client, password="a-brand-new-password")
    assert refresh(client, fresh["refresh_token"])[0] == 200


def test_unknown_refresh_token_is_rejected(client: TestClient) -> None:
    assert refresh(client, str(uuid.uuid4()))[0] == 401
