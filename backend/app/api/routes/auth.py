"""Authentication endpoints. Thin: all rules live in the services.

Every route here is unauthenticated, so this module is the whole public attack
surface: registration, token issuance, rotation and revocation.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    AccountThrottleDep,
    AuthServiceDep,
    CallerThrottleDep,
    UserServiceDep,
)
from app.core.config import settings
from app.models import (
    Envelope,
    ErrorResponse,
    Message,
    RefreshRequest,
    Token,
    UserCreate,
    UserPublic,
)
from app.services import TokenPair
from app.services.exceptions import InvalidCredentialsError, TooManyLoginAttemptsError

router = APIRouter(prefix="/auth", tags=["auth"])

_bad_credentials = {400: {"model": ErrorResponse, "description": "Incorrect email or password"}}
_invalid_refresh = {
    401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"}
}
_conflict = {409: {"model": ErrorResponse, "description": "Email already in use"}}
_invalid = {422: {"model": ErrorResponse, "description": "One or more fields are invalid"}}
_throttled = {429: {"model": ErrorResponse, "description": "Too many failed attempts"}}


@router.post(
    "/register",
    response_model=Envelope[UserPublic],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    responses={**_conflict, **_invalid},
)
def register_user(
    service: UserServiceDep, user_in: UserCreate, response: Response
) -> Envelope[UserPublic]:
    """Create an account and point `Location` at the new user resource."""
    user = service.register(user_in)
    # Absolute path including the `/api/v1` prefix applied in `api/main.py`;
    # a bare `/users/<id>` would not resolve for the client.
    response.headers["Location"] = f"{settings.API_V1_STR}/users/{user.id}"
    return Envelope(data=UserPublic.model_validate(user))


def _to_token(pair: TokenPair) -> Envelope[Token]:
    token = Token(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )
    return Envelope(data=token)


@router.post(
    "/access-token",
    response_model=Envelope[Token],
    summary="Log in for a token pair",
    responses={**_bad_credentials, **_throttled},
)
def log_in(
    service: AuthServiceDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    accounts: AccountThrottleDep,
    callers: CallerThrottleDep,
) -> Envelope[Token]:
    """Exchange credentials for a token pair, with a failed-attempt throttle."""
    email = form_data.username.strip().lower()
    caller = request.client.host if request.client else "unknown"
    account_key = f"account:{email}"
    caller_key = f"caller:{caller}"

    if accounts.retry_after(account_key) is not None or callers.retry_after(caller_key) is not None:
        raise TooManyLoginAttemptsError

    try:
        pair = service.login(email=form_data.username, password=form_data.password)
    except InvalidCredentialsError:
        # Only failures count, so a busy-but-successful client is never blocked.
        accounts.record_failure(account_key)
        callers.record_failure(caller_key)
        raise

    accounts.reset(account_key)
    return _to_token(pair)


@router.post(
    "/refresh-token",
    response_model=Envelope[Token],
    summary="Exchange a refresh token",
    responses={**_invalid_refresh, **_invalid},
)
def refresh_tokens(service: AuthServiceDep, payload: RefreshRequest) -> Envelope[Token]:
    """Rotate a refresh token into a new token pair (single use)."""
    return _to_token(service.refresh(refresh_token=payload.refresh_token))


@router.post(
    "/logout",
    response_model=Envelope[Message],
    summary="Revoke a session",
    responses={200: {"description": "Always succeeds, even for unknown tokens"}},
)
def log_out(service: AuthServiceDep, payload: RefreshRequest) -> Envelope[Message]:
    """Revoke the session chain owning this refresh token."""
    service.logout(refresh_token=payload.refresh_token)
    return Envelope(data=Message(message="Logged out"))
