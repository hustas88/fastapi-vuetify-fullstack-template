"""User endpoints. Thin: all rules live in `UserService`.

Everything here requires a token: self-service registration lives in
`routes/auth.py` (`POST /auth/register`), so this namespace has no public
endpoint to remember.

REST contract:

* `200 OK` for reads and updates, always shaped by `UserPublic`.
* `204 No Content` on delete — nothing meaningful left to return.
"""

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentSuperuser, CurrentUser, UserServiceDep
from app.api.params import PageParamsDep
from app.models import Envelope, ErrorResponse, PaginatedEnvelope, UserPublic, UserUpdate, paginated

router = APIRouter(prefix="/users", tags=["users"])

_unauthorized = {401: {"model": ErrorResponse, "description": "Not authenticated"}}
_forbidden = {403: {"model": ErrorResponse, "description": "Insufficient privileges"}}
_not_found = {404: {"model": ErrorResponse, "description": "User not found"}}
_conflict = {409: {"model": ErrorResponse, "description": "Email already in use"}}
_invalid = {422: {"model": ErrorResponse, "description": "One or more fields are invalid"}}


@router.get(
    "/me",
    response_model=Envelope[UserPublic],
    summary="Current user",
    responses=_unauthorized,
)
def read_user_me(current_user: CurrentUser) -> Envelope[UserPublic]:
    return Envelope(data=UserPublic.model_validate(current_user))


@router.patch(
    "/me",
    response_model=Envelope[UserPublic],
    summary="Update the current user",
    responses={**_unauthorized, **_conflict, **_invalid},
)
def update_user_me(
    service: UserServiceDep, current_user: CurrentUser, user_in: UserUpdate
) -> Envelope[UserPublic]:
    user = service.update_profile(current_user, user_in)
    return Envelope(data=UserPublic.model_validate(user))


@router.get(
    "/",
    response_model=PaginatedEnvelope[UserPublic],
    summary="List users (superuser)",
    responses={**_unauthorized, **_forbidden, **_invalid},
)
def read_users(
    service: UserServiceDep,
    params: PageParamsDep,
    _admin: CurrentSuperuser,
    response: Response,
) -> PaginatedEnvelope[UserPublic]:
    """One page of users, newest first unless `?sort=` says otherwise."""
    users, total_count = service.list_page(
        page=params.page,
        per_page=params.per_page,
        search=params.search,
        sort=params.sort,
    )
    # Also surfaced as a header, for clients that page without reading the body.
    response.headers["X-Total-Count"] = str(total_count)
    return paginated(
        [UserPublic.model_validate(user) for user in users],
        total_count=total_count,
        page=params.page,
        per_page=params.per_page,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a user (superuser)",
    responses={**_unauthorized, **_forbidden, **_not_found},
)
def delete_user(service: UserServiceDep, admin: CurrentSuperuser, user_id: uuid.UUID) -> Response:
    service.delete(user_id=user_id, actor=admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
