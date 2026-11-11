"""Shared persistence primitives for repositories backed by a SQLModel session.

Repositories own their session and commit their own writes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select


class SqlRepository:
    """Persistence primitives common to every SQL-backed repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save[T](self, entity: T) -> T:
        """Insert or update one entity and return the refreshed instance.

        `Session.add` handles both, so this is the single write primitive;
        specialised `add(...)` methods build the entity and delegate here.
        """
        self._session.add(entity)
        self._commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: object) -> None:
        self._session.delete(entity)
        self._commit()

    def _commit_all[T](self, entities: Iterable[T], *, commit: bool = True) -> int:
        """Flush an already-mutated batch, optionally inside the caller's transaction.

        `commit=False` stages the mutations so several repository calls can be
        committed together; the caller is then responsible for committing.
        Returns how many entities were written, so callers can report counts.
        """
        batch = list(entities)
        if not batch:
            return 0
        self._session.add_all(batch)
        if commit:
            self._commit()
        return len(batch)

    def _commit(self) -> None:
        """Commit, leaving the session usable when a constraint rejects the write."""
        try:
            self._session.commit()
        except IntegrityError:
            # A failed flush poisons the session; roll back so the caller can
            # translate the violation (e.g. duplicate email -> 409) and keep
            # using the same session.
            self._session.rollback()
            raise

    def fetch_page(
        self,
        model: Any,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
        search_fields: Sequence[Any] = (),
        order_by: Sequence[Any] = (),
        conditions: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[list[Any], int]:
        """Return one page of `model` rows plus the total row count.

        Search is a case-insensitive `ILIKE` across `search_fields`; LIKE
        wildcards in the term are escaped so a `%` from a client matches a
        literal `%` instead of the whole table. `order_by` should end with a
        unique column so paging is stable — otherwise rows can repeat or vanish
        between requests.
        """
        statement = select(model)
        if conditions:
            statement = statement.where(*conditions)
        if search and search_fields:
            pattern = f"%{_escape_like(search)}%"
            statement = statement.where(
                or_(*(field.ilike(pattern, escape="\\") for field in search_fields))
            )

        total = self._session.exec(select(func.count()).select_from(statement.subquery())).one()
        rows = self._session.exec(statement.order_by(*order_by).offset(offset).limit(limit))
        return list(rows.all()), int(total)


def _escape_like(term: str) -> str:
    """Escape LIKE metacharacters so user input is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
