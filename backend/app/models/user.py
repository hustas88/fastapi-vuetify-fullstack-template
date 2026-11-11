"""User domain: the `users` table and its API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from app.models.common import new_id, utcnow


class UserBase(SQLModel):
    # RFC 5321 caps an email address at 254 characters.
    email: EmailStr = Field(index=True, unique=True, max_length=254)
    full_name: str | None = Field(default=None, max_length=255)


class User(UserBase, table=True):
    """The `users` table.

    Columns are declared explicitly rather than inherited from `UserBase`:
    SQLAlchemy emits inherited columns first, which would place `id` after the
    base fields. `id` always comes first here, and table names are plural.
    """

    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=new_id, primary_key=True)
    email: EmailStr = Field(index=True, unique=True, max_length=254)
    # Argon2id encoded hash: 97 characters today (salt + digest + params).
    # The bound leaves room for stronger parameters or a different algorithm.
    password: str = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True, sa_column_kwargs={"server_default": sa.true()})
    is_superuser: bool = Field(default=False, sa_column_kwargs={"server_default": sa.false()})
    # Revocation epoch. Bumped on password change; `SMALLINT` is plenty for a
    # counter that increments once per credential change (max 32767).
    token_version: int = Field(
        default=0,
        sa_type=sa.SmallInteger,
        sa_column_kwargs={"server_default": sa.text("0")},
    )
    # `server_default` means the database fills these in, so inserts that bypass
    # the ORM still get timestamps.
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": sa.func.now()},
    )
    # Postgres has no `ON UPDATE` column clause (unlike MySQL) — the equivalent
    # needs a plpgsql function plus a trigger — so the bump is application-level
    # via `onupdate`, which also works in the SQLite test suite.
    updated_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": sa.func.now(), "onupdate": utcnow},
    )

    def record_credential_change(self, *, password_hash: str) -> None:
        """Apply a new password and revoke every access token issued so far.

        Refresh tokens must be revoked separately by the service layer, because
        that needs database access.
        """
        self.password = password_hash
        self.token_version += 1


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(SQLModel):
    email: EmailStr | None = None
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserPublic(UserBase):
    id: uuid.UUID
    is_active: bool
