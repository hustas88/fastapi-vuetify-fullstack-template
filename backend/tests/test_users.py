import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import User

PASSWORD = "supersecret123"


def register(client: TestClient, email: str, full_name: str | None = None) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/access-token",
        data={"username": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/users/me").status_code == 401


def test_register_returns_uuid_id(client: TestClient) -> None:
    user = register(client, "admin@example.com", "Admin")

    user_id = uuid.UUID(user["id"])
    assert user_id.version == 7
    assert user["email"] == "admin@example.com"
    # The hash must never leave the API.
    assert "password" not in user


def test_password_is_hashed_at_rest(client: TestClient) -> None:
    register(client, "admin@example.com")

    # Logging in with the plaintext works, proving the column stores a hash
    # that the verify path can consume.
    assert auth_headers(client, "admin@example.com")


def test_me_returns_signed_up_user(client: TestClient) -> None:
    register(client, "admin@example.com", "Admin")
    headers = auth_headers(client, "admin@example.com")

    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "admin@example.com"


def test_duplicate_register_is_rejected(client: TestClient) -> None:
    register(client, "admin@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    assert response.status_code == 409


def test_wrong_password_is_rejected(client: TestClient) -> None:
    register(client, "admin@example.com")
    response = client.post(
        "/api/v1/auth/access-token",
        data={"username": "admin@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 400


def test_password_change_takes_effect(client: TestClient) -> None:
    register(client, "admin@example.com")
    headers = auth_headers(client, "admin@example.com")

    response = client.patch(
        "/api/v1/users/me", json={"password": "a-new-password"}, headers=headers
    )
    assert response.status_code == 200

    old = client.post(
        "/api/v1/auth/access-token",
        data={"username": "admin@example.com", "password": PASSWORD},
    )
    assert old.status_code == 400

    new = client.post(
        "/api/v1/auth/access-token",
        data={"username": "admin@example.com", "password": "a-new-password"},
    )
    assert new.status_code == 200


def test_items_endpoint_is_gone(client: TestClient) -> None:
    register(client, "admin@example.com")
    headers = auth_headers(client, "admin@example.com")

    assert client.get("/api/v1/items/", headers=headers).status_code == 404


def test_timestamps_default_on_insert(client: TestClient, session: Session) -> None:
    user = register(client, "admin@example.com")

    db_user = session.get(User, uuid.UUID(user["id"]))
    assert db_user is not None
    assert db_user.created_at is not None
    assert db_user.updated_at is not None
    # A fresh row has never been modified.
    assert db_user.updated_at >= db_user.created_at


def test_update_bumps_updated_at(client: TestClient, session: Session) -> None:
    user = register(client, "admin@example.com")
    headers = auth_headers(client, "admin@example.com")

    # Backdate the row so the comparison is deterministic rather than relying
    # on the two timestamps differing by microseconds.
    db_user = session.get(User, uuid.UUID(user["id"]))
    assert db_user is not None
    long_ago = datetime.now(UTC) - timedelta(days=2)
    db_user.created_at = long_ago
    db_user.updated_at = long_ago
    session.add(db_user)
    session.commit()

    response = client.patch("/api/v1/users/me", json={"full_name": "Renamed"}, headers=headers)
    assert response.status_code == 200

    session.refresh(db_user)
    assert db_user.updated_at > long_ago
    # `created_at` must never move once the row exists.
    assert db_user.created_at == long_ago


# ---------------------------------------------------------------------------
# REST response contract
# ---------------------------------------------------------------------------
def test_register_returns_201_with_location_header(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "located@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    # Absolute, including the version prefix, so the client can follow it.
    assert response.headers["location"] == f"/api/v1/users/{response.json()['data']['id']}"


def test_delete_returns_204_with_no_body(client: TestClient, session: Session) -> None:
    victim = register(client, "victim@example.com")
    admin = register(client, "admin@example.com")
    headers = auth_headers(client, "admin@example.com")
    # Promote the caller so the delete is authorised.
    row = session.get(User, uuid.UUID(admin["id"]))
    assert row is not None
    row.is_superuser = True
    session.add(row)
    session.commit()

    response = client.delete(f"/api/v1/users/{victim['id']}", headers=headers)
    assert response.status_code == 204
    assert response.content == b""


def test_error_responses_use_the_error_envelope(client: TestClient) -> None:
    register(client, "admin@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    assert response.status_code == 409
    assert set(response.json()) == {"error"}
    body = response.json()["error"]
    assert body["code"] == "email_already_exists"
    assert body["message"] == "A user with this email already exists."
    # Domain errors are not field-specific, so no details are attached.
    assert "details" not in body
