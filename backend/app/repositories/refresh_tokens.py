"""Data access for refresh tokens (session records)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select

from app.models import RefreshToken, utcnow
from app.repositories.base import SqlRepository


class RefreshTokenRepository(SqlRepository):
    def add(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        family_id: uuid.UUID,
        expires_at: datetime,
    ) -> RefreshToken:
        return self.save(
            RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                family_id=family_id,
                expires_at=expires_at,
            )
        )

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        statement = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self._session.exec(statement).first()

    def consume(self, token_hash: str, *, now: datetime) -> bool:
        """Mark a token used, atomically. True only for the request that won.

        A single conditional `UPDATE` is what makes rotation replay-safe: two
        concurrent refreshes of the same token both used to read
        `revoked_at IS NULL` and both succeed, handing an attacker a parallel
        session. Now the database decides, and the loser sees zero rows changed.
        """
        statement = (
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = self._session.execute(statement)
        self._session.commit()
        return result.rowcount == 1

    def revoke_family(self, family_id: uuid.UUID, *, commit: bool = True) -> int:
        """Revoke every token in one session chain. Returns how many changed."""
        return self._revoke_where(RefreshToken.family_id == family_id, commit=commit)

    def revoke_all_for_user(self, user_id: uuid.UUID, *, commit: bool = True) -> int:
        """Revoke every session belonging to a user."""
        return self._revoke_where(RefreshToken.user_id == user_id, commit=commit)

    def _revoke_where(self, condition: ColumnElement[bool], *, commit: bool = True) -> int:
        statement = select(RefreshToken).where(condition, RefreshToken.revoked_at.is_(None))
        records = list(self._session.exec(statement).all())
        now = utcnow()
        for record in records:
            record.revoke(now=now)
        return self._commit_all(records, commit=commit)
