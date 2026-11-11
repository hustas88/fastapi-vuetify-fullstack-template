"""Shared primitives and API vocabulary used by every domain.

Nothing here knows about users or sessions; it is the glue that schemas across
the app agree on (timestamps, IDs, error and paging envelopes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from math import ceil

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    """Return a time-ordered UUID (v7).

    The embedded timestamp keeps inserts at the end of the B-tree index, which
    is far better for locality than random v4 identifiers.
    """
    return uuid.uuid7()


class Message(SQLModel):
    message: str


# ---------------------------------------------------------------------------
# Errors (`api/errors.py` builds these; OpenAPI documents them via routes)
# ---------------------------------------------------------------------------
class ErrorDetail(SQLModel):
    """One offending field (validation errors only)."""

    field: str
    message: str


class ErrorBody(SQLModel):
    """Stable `code` for programs, readable `message` for people."""

    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(SQLModel):
    """Shape of every error returned by the API (`api/errors.py`)."""

    error: ErrorBody


# ---------------------------------------------------------------------------
# Response envelopes
#
# Every success response is `{"data": ...}` so a client always knows where the
# payload is, whatever the resource looks like. Collections add `meta` with the
# paging summary — the JSON:API arrangement (`data` / `meta` / `links`), which
# leaves room for links or warnings later without breaking the shape.
# ---------------------------------------------------------------------------
class Envelope[T](BaseModel):
    """Wrapper around a single resource."""

    data: T


class PageMeta(SQLModel):
    """Paging summary for a collection response."""

    total_count: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedEnvelope[T](BaseModel):
    """Wrapper around one page of a collection."""

    data: list[T]
    meta: PageMeta


def paginated[T](
    items: list[T],
    *,
    total_count: int,
    page: int,
    per_page: int,
) -> PaginatedEnvelope[T]:
    """Build the envelope for a collection page, deriving the counts once."""
    total_pages = ceil(total_count / per_page) if per_page else 0
    return PaginatedEnvelope[T](
        data=items,
        meta=PageMeta(
            total_count=total_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )
