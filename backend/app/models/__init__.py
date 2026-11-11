"""Domain models, split by aggregate.

Importing this package registers every table on `SQLModel.metadata`, which is
what `create_all` and Alembic autogenerate rely on — so new modules must be
re-exported below.

The re-exports keep the import style stable: `from app.models import User`
works regardless of which module a symbol actually lives in.
"""

from app.models.auth import RefreshRequest, RefreshToken, Token
from app.models.common import (
    Envelope,
    ErrorBody,
    ErrorDetail,
    ErrorResponse,
    Message,
    PageMeta,
    PaginatedEnvelope,
    new_id,
    paginated,
    utcnow,
)
from app.models.user import User, UserBase, UserCreate, UserPublic, UserUpdate

__all__ = [
    # auth
    "RefreshRequest",
    "RefreshToken",
    "Token",
    # common
    "Envelope",
    "ErrorBody",
    "ErrorDetail",
    "ErrorResponse",
    "Message",
    "PageMeta",
    "PaginatedEnvelope",
    "new_id",
    "paginated",
    "utcnow",
    # user
    "User",
    "UserBase",
    "UserCreate",
    "UserPublic",
    "UserUpdate",
]
