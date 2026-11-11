"""Data access for users."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlmodel import select

from app.models import User, UserCreate
from app.repositories.base import SqlRepository


class UserRepository(SqlRepository):
    # Which columns a caller may sort by. Anything else is rejected upstream, so
    # a query-string value can never reach the ORDER BY clause unchecked.
    SORTABLE: dict[str, Any] = {
        "created_at": User.created_at,
        "updated_at": User.updated_at,
        "email": User.email,
        "full_name": User.full_name,
        "is_active": User.is_active,
        "is_superuser": User.is_superuser,
    }
    # Columns matched by `?q=`.
    SEARCHABLE: tuple[Any, ...] = (User.email, User.full_name)

    def get(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self._session.exec(statement).first()

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    def add(self, data: UserCreate, *, password_hash: str) -> User:
        """Register a new user. Hashing happens in the service layer."""
        return self.save(User.model_validate(data, update={"password": password_hash}))

    def list_page(
        self,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
        order_by: Sequence[Any] = (),
    ) -> tuple[list[User], int]:
        """One page of users, plus the total count for the pager."""
        return self.fetch_page(
            User,
            offset=offset,
            limit=limit,
            search=search,
            search_fields=self.SEARCHABLE,
            # `id` breaks ties so identical timestamps cannot shuffle rows
            # between pages.
            order_by=[*order_by, User.id],
        )
