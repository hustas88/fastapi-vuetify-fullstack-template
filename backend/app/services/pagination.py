"""Pagination and sorting helpers shared by every collection endpoint.

Keeping this next to the services (rather than in the API layer) means a
repository list can be paged from anywhere — a route, a background job, a test —
and the sorting allowlist is still enforced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.exceptions import InvalidSortFieldError

#: More clauses than this cannot be useful on a grid and would let a caller
#: inflate the generated SQL arbitrarily.
MAX_SORT_FIELDS = 5


def resolve_order_by(
    sort: str | None,
    allowed: Mapping[str, Any],
    *,
    default: str = "-created_at",
) -> list[Any]:
    """Translate `sort=-email` into SQLAlchemy ordering clauses.

    Only names in `allowed` survive: the parameter comes straight from the query
    string, so an unchecked value would let a caller order by any column (or a
    related table) and enumerate data they cannot otherwise see.
    """
    requested = [field.strip() for field in (sort or "").split(",") if field.strip()]
    if not requested:
        requested = [default]
    if len(requested) > MAX_SORT_FIELDS:
        raise InvalidSortFieldError(f"Sort supports at most {MAX_SORT_FIELDS} fields")

    clauses: list[Any] = []
    for raw in requested:
        descending = raw.startswith("-")
        name = raw.lstrip("-+")
        column = allowed.get(name)
        if column is None:
            options = ", ".join(sorted(allowed))
            raise InvalidSortFieldError(f"Cannot sort by '{name}'. Choose one of: {options}")
        clauses.append(column.desc() if descending else column.asc())
    return clauses
