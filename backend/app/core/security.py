"""Security primitives, expressed as collaborating objects.

Each class owns one concern and can be swapped or faked in tests:

* `PasswordHasher`         — password verification/hashing (Argon2id).
* `AccessTokenCodec`       — mints and verifies signed JWTs.
* `RefreshTokenGenerator`  — opaque refresh-token generation and digesting.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

# Only HS256 is ever accepted. Pinning a single algorithm is what prevents
# "algorithm confusion" attacks (e.g. a token claiming `alg: none`, or a token
# signed with a public key as if it were an HMAC secret).
ALGORITHM = "HS256"

# Every token must carry these claims; `jwt.decode(..., options={"require": ...})`
# rejects a token that omits any of them, even if the signature is valid.
REQUIRED_CLAIMS = ("exp", "iat", "sub", "iss", "aud", "jti", "ver")

# Raised for any verification failure (bad signature, expiry, wrong claims...).
TOKEN_ERRORS = (jwt.PyJWTError, KeyError, TypeError, ValueError)


class PasswordHasher:
    """Hashes and verifies passwords, and can burn time to hide timing leaks."""

    _PLACEHOLDER = "timing-equalization-placeholder"

    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()
        self._dummy_hash: str | None = None

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._hasher.verify(password, password_hash)

    def equalize_timing(self, password: str) -> None:
        """Burn the same work as a real verification for an unknown user.

        Without this, an attacker can distinguish "no such user" from "wrong
        password" by response time alone and enumerate accounts.
        """
        if self._dummy_hash is None:
            self._dummy_hash = self.hash(self._PLACEHOLDER)
        self.verify(password, self._dummy_hash)


class AccessTokenCodec:
    """Creates and verifies the signed access tokens (HS256 JWTs)."""

    def __init__(
        self,
        secret_key: str,
        issuer: str,
        audience: str,
        lifetime_minutes: int,
    ) -> None:
        self._secret_key = secret_key
        self._issuer = issuer
        self._audience = audience
        self._lifetime = timedelta(minutes=lifetime_minutes)

    @property
    def lifetime_seconds(self) -> int:
        return int(self._lifetime.total_seconds())

    def encode(self, subject: str | uuid.UUID, *, token_version: int) -> str:
        """Sign a token for `subject` carrying the user's revocation epoch."""
        now = datetime.now(UTC)
        payload = {
            "sub": str(subject),
            "iat": now,
            "exp": now + self._lifetime,
            "iss": self._issuer,
            "aud": self._audience,
            "jti": str(uuid.uuid4()),
            "ver": token_version,
        }
        return jwt.encode(payload, self._secret_key, algorithm=ALGORITHM)

    def decode(self, token: str) -> dict[str, object]:
        """Verify signature, algorithm and claims; raise from `TOKEN_ERRORS`."""
        return jwt.decode(
            token,
            self._secret_key,
            algorithms=[ALGORITHM],
            audience=self._audience,
            issuer=self._issuer,
            options={"require": list(REQUIRED_CLAIMS)},
        )


class RefreshTokenGenerator:
    """Generates opaque refresh tokens and the digests used to store them."""

    # 32 bytes of entropy -> 43 URL-safe characters. Refresh tokens are opaque
    # bearer credentials, not JWTs: they must be revocable, which needs a lookup.
    TOKEN_BYTES = 32

    def generate(self) -> str:
        return secrets.token_urlsafe(self.TOKEN_BYTES)

    def digest(self, token: str) -> str:
        """Return the stored digest of a token.

        A fast hash is correct here (unlike passwords): the input is 256 random
        bits, so there is nothing to brute-force, and lookups must stay cheap.
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return PasswordHasher()


@lru_cache
def get_access_token_codec() -> AccessTokenCodec:
    return AccessTokenCodec(
        secret_key=settings.SECRET_KEY,
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
        lifetime_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )


@lru_cache
def get_refresh_token_generator() -> RefreshTokenGenerator:
    return RefreshTokenGenerator()
