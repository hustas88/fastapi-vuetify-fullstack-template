"""User account management."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError

from app.core.security import PasswordHasher
from app.models import User, UserCreate, UserUpdate
from app.repositories import RefreshTokenRepository, UserRepository
from app.services.exceptions import (
    CannotDeleteSelfError,
    EmailAlreadyExistsError,
    UserNotFoundError,
)
from app.services.pagination import resolve_order_by


class UserService:
    """Registration, profile updates and account deletion."""

    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        password_hasher: PasswordHasher,
        superuser_email: str | None = None,
        superuser_password: str | None = None,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._password_hasher = password_hasher
        self._superuser_email = superuser_email
        self._superuser_password = superuser_password

    def register(self, data: UserCreate) -> User:
        if self._users.email_exists(data.email):
            raise EmailAlreadyExistsError
        try:
            return self._users.add(data, password_hash=self._password_hasher.hash(data.password))
        except IntegrityError as exc:
            # Two concurrent registrations can both pass `email_exists`; the
            # unique index is the real arbiter, and its failure is a 409 too.
            raise EmailAlreadyExistsError from exc

    def update_profile(self, user: User, data: UserUpdate) -> User:
        changes = data.model_dump(exclude_unset=True)

        new_email = changes.get("email")
        if new_email and new_email != user.email and self._users.email_exists(new_email):
            raise EmailAlreadyExistsError

        new_password = changes.pop("password", None)
        if new_password:
            user.record_credential_change(password_hash=self._password_hasher.hash(new_password))
            # Staged in the same transaction as the save below, so the password
            # and the revocation land together or not at all.
            self._refresh_tokens.revoke_all_for_user(user.id, commit=False)

        user.sqlmodel_update(changes)
        try:
            return self._users.save(user)
        except IntegrityError as exc:
            raise EmailAlreadyExistsError from exc

    def get(self, user_id: uuid.UUID) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFoundError
        return user

    def list_page(
        self,
        *,
        page: int,
        per_page: int,
        search: str | None = None,
        sort: str | None = None,
    ) -> tuple[list[User], int]:
        """One page of users for the admin grid, with the total row count."""
        order_by = resolve_order_by(sort, self._users.SORTABLE)
        return self._users.list_page(
            offset=(page - 1) * per_page,
            limit=per_page,
            search=search,
            order_by=order_by,
        )

    def delete(self, *, user_id: uuid.UUID, actor: User) -> None:
        if user_id == actor.id:
            raise CannotDeleteSelfError
        self._users.delete(self.get(user_id))

    def ensure_superuser(self) -> bool:
        """Create the configured superuser if it does not exist yet.

        Returns True when a user was created. Used on startup so a fresh local
        database is immediately usable.
        """
        email = self._superuser_email
        password = self._superuser_password
        if not email or not password or self._users.email_exists(email):
            return False

        self._users.add(
            UserCreate(email=email, password=password, full_name="Admin"),
            password_hash=self._password_hasher.hash(password),
        )
        created = self._users.get_by_email(email)
        if created is not None:
            created.is_superuser = True
            self._users.save(created)
        return True
