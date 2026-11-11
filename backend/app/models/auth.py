"""Authentication domain: token payloads and the refresh-token session table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models.common import new_id, utcnow


class Token(SQLModel):
    """Token pair returned by the auth endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # Access-token lifetime in seconds, so clients can refresh proactively.
    expires_in: int


class RefreshRequest(SQLModel):
    refresh_token: str


class RefreshToken(SQLModel, table=True):
    """A server-side record enabling long-lived, revocable sessions.

    The token itself is an opaque random string; only its SHA-256 digest is
    stored, so a database leak does not hand out usable credentials.
    """

    __tablename__ = "refresh_tokens"

    id: uuid.UUID = Field(default_factory=new_id, primary_key=True)
    # `ondelete="CASCADE"`: deleting a user removes their sessions. Without it
    # the FK would block the delete and the API would answer 500.
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    # SHA-256 hex digest (64 chars) of the opaque token handed to the client.
    token_hash: str = Field(index=True, unique=True, max_length=64)
    # Session chain id. Every rotation keeps it, so replaying a used token can
    # revoke exactly that chain without logging out other devices.
    family_id: uuid.UUID = Field(index=True)
    expires_at: datetime = Field(nullable=False)
    revoked_at: datetime | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": sa.func.now()},
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Whether the idle window has passed.

        SQLite drops tzinfo on round-trip, so comparisons normalise first.
        """
        current = now or utcnow()
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires <= current

    def revoke(self, *, now: datetime | None = None) -> None:
        self.revoked_at = now or utcnow()
