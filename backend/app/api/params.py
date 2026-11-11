"""Query-string contract shared by every grid endpoint.

`GET /api/v1/<collection>` accepts:

    ?page=2&per_page=25&q=acme&sort=-created_at,email

* `page` is 1-based; `per_page` is capped so a client cannot ask for the table.
* `q` is free-text search over the resource's declared searchable columns.
* `sort` is a comma separated allowlist of field names; a leading `-` means
  descending. Unknown fields are rejected (never passed to SQL).

Filters will be added later as sibling parameters; they compose with these
because paging/sorting/searching are applied by the same repository primitive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100
MAX_SORT_FIELDS = 5
# Long enough for `-created_at,email,full_name`, short enough that a client
# cannot send a wall of fields.
MAX_SORT_LENGTH = 200


@dataclass(frozen=True, slots=True)
class PageParams:
    """Validated paging/search/sort parameters for a collection request."""

    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1
    per_page: Annotated[
        int,
        Query(ge=1, le=MAX_PER_PAGE, description=f"Items per page (max {MAX_PER_PAGE})"),
    ] = DEFAULT_PER_PAGE
    q: Annotated[str | None, Query(max_length=100, description="Free-text search")] = None
    sort: Annotated[
        str | None,
        Query(
            max_length=MAX_SORT_LENGTH,
            description='Comma separated fields; prefix a field with "-" for descending',
        ),
    ] = None

    @property
    def search(self) -> str | None:
        """The search term, or None when it is absent or whitespace."""
        term = (self.q or "").strip()
        return term or None


PageParamsDep = Annotated[PageParams, Depends()]
