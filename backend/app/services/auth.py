"""Authentication: credential checks and token lifecycle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from app.core.security import AccessTokenCodec, PasswordHasher, RefreshTokenGenerator
from app.models import User, utcnow
from app.repositories import RefreshTokenRepository, UserRepository
from app.services.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)


@dataclass(frozen=True)
class TokenPair:
    """The credentials handed to a client after a successful authentication."""

    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    """Owns authentication and the token lifecycle.

    Invariants it maintains:

    * An unknown email and a wrong password are indistinguishable — same error,
      same timing.
    * Every refresh rotates: the presented token is consumed and a new one joins
      the same family.
    * Presenting a consumed token is treated as replay and revokes the family.
    * "Idle" expiry: each refresh pushes the window forward.
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        password_hasher: PasswordHasher,
        token_codec: AccessTokenCodec,
        token_generator: RefreshTokenGenerator,
        refresh_token_lifetime_days: int,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._password_hasher = password_hasher
        self._token_codec = token_codec
        self._token_generator = token_generator
        self._refresh_lifetime = timedelta(days=refresh_token_lifetime_days)

    # -- credentials -------------------------------------------------------
    def authenticate(self, *, email: str, password: str) -> User:
        user = self._users.get_by_email(email)
        if user is None:
            # Burn equivalent time so response latency does not reveal whether
            # the account exists.
            self._password_hasher.equalize_timing(password)
            raise InvalidCredentialsError
        if not self._password_hasher.verify(password, user.password):
            raise InvalidCredentialsError
        if not user.is_active:
            raise InactiveUserError
        return user

    # -- tokens ------------------------------------------------------------
    def login(self, *, email: str, password: str) -> TokenPair:
        user = self.authenticate(email=email, password=password)
        return self.issue_token_pair(user)

    def issue_token_pair(self, user: User, *, family_id: uuid.UUID | None = None) -> TokenPair:
        """Mint an access token plus a fresh refresh token."""
        plaintext = self._token_generator.generate()
        self._refresh_tokens.add(
            user_id=user.id,
            token_hash=self._token_generator.digest(plaintext),
            family_id=family_id or uuid.uuid7(),
            expires_at=utcnow() + self._refresh_lifetime,
        )
        access_token = self._token_codec.encode(user.id, token_version=user.token_version)
        return TokenPair(
            access_token=access_token,
            refresh_token=plaintext,
            expires_in=self._token_codec.lifetime_seconds,
        )

    def refresh(self, *, refresh_token: str) -> TokenPair:
        """Rotate a refresh token into a new pair."""
        record = self._refresh_tokens.get_by_token_hash(self._token_generator.digest(refresh_token))
        if record is None:
            raise InvalidRefreshTokenError

        if record.is_revoked:
            # Already exchanged: either a stolen copy is being replayed or the
            # client retried. Either way the chain is no longer trustworthy.
            self._refresh_tokens.revoke_family(record.family_id)
            raise InvalidRefreshTokenError

        if record.is_expired():
            raise InvalidRefreshTokenError

        user = self._users.get(record.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError

        # Atomic single-use check: exactly one concurrent caller can flip
        # `revoked_at`. Losing the race means the token was presented twice, so
        # treat it the same as a replay of an already-revoked token.
        if not self._refresh_tokens.consume(record.token_hash, now=utcnow()):
            self._refresh_tokens.revoke_family(record.family_id)
            raise InvalidRefreshTokenError

        return self.issue_token_pair(user, family_id=record.family_id)

    def logout(self, *, refresh_token: str) -> None:
        """Revoke the chain owning this token. Never reveals whether it existed."""
        record = self._refresh_tokens.get_by_token_hash(self._token_generator.digest(refresh_token))
        if record is not None:
            self._refresh_tokens.revoke_family(record.family_id)
