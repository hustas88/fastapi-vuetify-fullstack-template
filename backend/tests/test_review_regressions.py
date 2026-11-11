"""Regression tests for the issues found in code review."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.db import Database
from app.core.security import RefreshTokenGenerator, get_password_hasher
from app.core.throttle import ACCOUNT_LIMIT
from app.models import RefreshToken, User, UserCreate
from app.repositories import RefreshTokenRepository, UserRepository
from app.services import UserService
from app.services.exceptions import EmailAlreadyExistsError

PASSWORD = "supersecret123"


def register(client: TestClient, email: str = "user@example.com") -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def login(client: TestClient, email: str = "user@example.com", password: str = PASSWORD) -> dict:
    response = client.post(
        "/api/v1/auth/access-token", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def as_superuser(client: TestClient, session: Session, email: str = "admin@example.com") -> dict:
    user = register(client, email)
    row = session.get(User, uuid.UUID(user["id"]))
    assert row is not None
    row.is_superuser = True
    session.add(row)
    session.commit()
    tokens = login(client, email)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ---------------------------------------------------------------------------
# HIGH: deleting a user with session history
# ---------------------------------------------------------------------------
def test_deleting_a_user_with_sessions_cascades(client: TestClient, session: Session) -> None:
    headers = as_superuser(client, session)
    victim = register(client, "victim@example.com")
    # The victim signs in, so a `refresh_tokens` row points at them.
    login(client, "victim@example.com")

    response = client.delete(f"/api/v1/users/{victim['id']}", headers=headers)

    assert response.status_code == 204, response.text
    assert session.get(User, uuid.UUID(victim["id"])) is None


# ---------------------------------------------------------------------------
# MEDIUM: rotation is atomic
# ---------------------------------------------------------------------------
def test_consume_is_single_use(client: TestClient, session: Session) -> None:
    register(client)
    tokens = login(client)
    repository = RefreshTokenRepository(session)
    token_hash = RefreshTokenGenerator().digest(tokens["refresh_token"])
    now = datetime.now(UTC)

    assert repository.consume(token_hash, now=now) is True
    # A competing refresh loses: the row is already revoked.
    assert repository.consume(token_hash, now=now) is False


def test_sequential_replay_still_revokes_the_family(client: TestClient, session: Session) -> None:
    register(client)
    first = login(client)
    second = client.post(
        "/api/v1/auth/refresh-token", json={"refresh_token": first["refresh_token"]}
    ).json()["data"]

    replayed = client.post(
        "/api/v1/auth/refresh-token", json={"refresh_token": first["refresh_token"]}
    )
    assert replayed.status_code == 401
    # The sibling issued by rotation is dead too.
    sibling = client.post(
        "/api/v1/auth/refresh-token", json={"refresh_token": second["refresh_token"]}
    )
    assert sibling.status_code == 401

    revoked = session.exec(select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))).all()
    assert len(revoked) >= 2


# ---------------------------------------------------------------------------
# MEDIUM: bounded sort
# ---------------------------------------------------------------------------
def test_too_many_sort_fields_is_rejected(client: TestClient, session: Session) -> None:
    headers = as_superuser(client, session)

    # Six valid names, short enough to pass the length check.
    response = client.get("/api/v1/users/?sort=" + ",".join(["email"] * 6), headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_sort_field"


def test_oversized_sort_parameter_is_rejected(client: TestClient, session: Session) -> None:
    headers = as_superuser(client, session)

    response = client.get("/api/v1/users/?sort=" + ",".join(["email"] * 2000), headers=headers)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# MEDIUM: deployment defaults
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("password", ["changethis123", "changethis", "changeme", "password"])
def test_placeholder_superuser_password_is_refused_outside_local(password: str) -> None:
    with pytest.raises(ValueError, match="FIRST_SUPERUSER_PASSWORD"):
        Settings(
            _env_file=None,
            ENVIRONMENT="staging",
            SECRET_KEY="x" * 40,
            FIRST_SUPERUSER_PASSWORD=password,
        )


def test_local_environment_still_allows_examples() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="local",
        SECRET_KEY="x" * 40,
        FIRST_SUPERUSER_PASSWORD="changethis123",
    )
    assert settings.ENVIRONMENT == "local"


# ---------------------------------------------------------------------------
# MEDIUM: sign-in throttle
# ---------------------------------------------------------------------------
def test_repeated_failures_are_throttled(client: TestClient) -> None:
    register(client)

    for _ in range(ACCOUNT_LIMIT):
        response = client.post(
            "/api/v1/auth/access-token",
            data={"username": "user@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 400

    blocked = client.post(
        "/api/v1/auth/access-token",
        data={"username": "user@example.com", "password": "wrong-password"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_login_attempts"
    assert blocked.headers["retry-after"] == "60"


def test_successful_login_clears_failures(client: TestClient) -> None:
    register(client)

    for _ in range(ACCOUNT_LIMIT - 1):
        client.post(
            "/api/v1/auth/access-token",
            data={"username": "user@example.com", "password": "wrong-password"},
        )
    login(client)  # resets the account's budget
    # Still a 400, not a 429: the counter started over.
    assert (
        client.post(
            "/api/v1/auth/access-token",
            data={"username": "user@example.com", "password": "wrong-password"},
        ).status_code
        == 400
    )


# ---------------------------------------------------------------------------
# LOW: constraint races map to 409
# ---------------------------------------------------------------------------
def test_unique_violation_is_a_conflict(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client, "taken@example.com")
    service = UserService(
        users=UserRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        password_hasher=get_password_hasher(),
    )

    def add(*_args, **_kwargs):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(service._users, "add", add)  # noqa: SLF001

    with pytest.raises(EmailAlreadyExistsError):
        service.register(UserCreate(email="taken@example.com", password=PASSWORD))


# ---------------------------------------------------------------------------
# MEDIUM: startup keeps alembic_version in sync
# ---------------------------------------------------------------------------
def test_create_schema_runs_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    import alembic.command as alembic_command

    revisions: list[str] = []
    monkeypatch.setattr(
        alembic_command,
        "upgrade",
        lambda _config, revision: revisions.append(revision),
    )

    Database("sqlite://").create_schema()

    assert revisions == ["head"]


# ---------------------------------------------------------------------------
# LOW: CORS exposes the count header
# ---------------------------------------------------------------------------
def test_total_count_header_is_exposed(client: TestClient) -> None:
    response = client.get("/api/v1/health/", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-expose-headers"] == "X-Total-Count"
