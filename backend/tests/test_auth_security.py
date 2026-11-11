"""Tests that actively attempt to forge or abuse access tokens."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import Settings, settings
from app.core.security import ALGORITHM, get_access_token_codec
from app.models import User

PASSWORD = "supersecret123"

ME = "/api/v1/users/me"


def b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def register(client: TestClient, email: str = "victim@example.com") -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def valid_token(client: TestClient, email: str = "victim@example.com") -> str:
    response = client.post(
        "/api/v1/auth/access-token",
        data={"username": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def base_claims(**overrides: object) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid7()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "ver": 0,
    }
    claims.update(overrides)
    return claims


# ---------------------------------------------------------------------------
# Forgery
# ---------------------------------------------------------------------------
def test_token_signed_with_another_key_is_rejected(client: TestClient) -> None:
    user = register(client)
    forged = jwt.encode(
        base_claims(sub=str(user["id"])),
        "an-attackers-key-that-is-also-long-enough-to-sign",
        algorithm=ALGORITHM,
    )

    response = client.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_unsigned_token_is_rejected(client: TestClient) -> None:
    """`alg: none` must never be honoured."""
    user = register(client)
    # Build the classic unsigned token by hand rather than via `jwt.encode`.
    header = b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = b64encode(json.dumps(base_claims(sub=str(user["id"]))).encode())
    unsigned = f"{header}.{payload}."

    response = client.get(ME, headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


def test_tampered_payload_is_rejected(client: TestClient) -> None:
    register(client)
    token = valid_token(client)
    header, payload, signature = token.split(".")

    # Swap the subject for another user id, keeping the original signature.
    claims = json.loads(b64decode(payload))
    claims["sub"] = str(uuid.uuid7())
    tampered = f"{header}.{b64encode(json.dumps(claims).encode())}.{signature}"

    response = client.get(ME, headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------
def test_expired_token_is_rejected(client: TestClient) -> None:
    user = register(client)
    past = datetime.now(UTC) - timedelta(minutes=10)
    expired = jwt.encode(
        base_claims(
            sub=str(user["id"]),
            iat=int(past.timestamp()),
            exp=int((past + timedelta(minutes=1)).timestamp()),
        ),
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )

    assert client.get(ME, headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_wrong_audience_is_rejected(client: TestClient) -> None:
    user = register(client)
    token = jwt.encode(
        base_claims(sub=str(user["id"]), aud="some-other-service"),
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )

    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_wrong_issuer_is_rejected(client: TestClient) -> None:
    user = register(client)
    token = jwt.encode(
        base_claims(sub=str(user["id"]), iss="some-other-issuer"),
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )

    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "iss", "aud", "jti", "ver"])
def test_missing_required_claim_is_rejected(client: TestClient, missing: str) -> None:
    user = register(client)
    claims = base_claims(sub=str(user["id"]))
    claims.pop(missing)
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)

    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_non_uuid_subject_is_rejected(client: TestClient) -> None:
    register(client)
    token = jwt.encode(base_claims(sub="1"), settings.SECRET_KEY, algorithm=ALGORITHM)

    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------
def test_password_change_revokes_existing_tokens(client: TestClient) -> None:
    register(client)
    token = valid_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(ME, headers=headers).status_code == 200

    changed = client.patch(
        "/api/v1/users/me", json={"password": "a-brand-new-password"}, headers=headers
    )
    assert changed.status_code == 200

    # The token was valid a moment ago; the token_version bump invalidates it.
    assert client.get(ME, headers=headers).status_code == 401

    # A fresh login still works.
    response = client.post(
        "/api/v1/auth/access-token",
        data={"username": "victim@example.com", "password": "a-brand-new-password"},
    )
    assert response.status_code == 200


def test_token_for_deleted_user_is_rejected(client: TestClient, session: Session) -> None:
    user = register(client)
    token = valid_token(client)

    # Remove the row behind the token's back.
    db_user = session.get(User, uuid.UUID(user["id"]))
    assert db_user is not None
    session.delete(db_user)
    session.commit()

    response = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Token minting helper
# ---------------------------------------------------------------------------
def test_create_access_token_embeds_expected_claims() -> None:
    subject = str(uuid.uuid7())
    token = get_access_token_codec().encode(subject, token_version=3)
    claims = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )

    assert claims["sub"] == subject
    assert claims["ver"] == 3
    assert claims["iss"] == settings.JWT_ISSUER
    assert claims["aud"] == settings.JWT_AUDIENCE
    assert claims["jti"]


# ---------------------------------------------------------------------------
# Configuration guard rails
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("weak", ["changethis", "secret", f"{'a' * 31}"])
def test_short_secret_key_is_refused_outside_local(weak: str) -> None:
    """RFC 7518 §3.2 requires an HS256 key of at least 32 bytes."""
    assert len(weak) < 32
    with pytest.raises(ValueError, match="shorter than 32 characters"):
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY=weak)


def test_short_secret_key_is_only_a_warning_locally() -> None:
    with pytest.warns(UserWarning, match="Allowed only because ENVIRONMENT=local"):
        config = Settings(_env_file=None, ENVIRONMENT="local", SECRET_KEY="changethis")
    assert config.SECRET_KEY == "changethis"


def test_strong_secret_key_is_accepted_outside_local() -> None:
    config = Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="f" * 64)
    assert len(config.SECRET_KEY) == 64


def test_non_positive_token_lifetime_is_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        Settings(_env_file=None, SECRET_KEY="f" * 64, ACCESS_TOKEN_EXPIRE_MINUTES=0)
