"""Dependency wiring.

Routes depend on *services*, never on sessions or repositories directly. Each
provider is overridable in tests via `app.dependency_overrides`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.config import settings
from app.core.db import get_session
from app.core.security import (
    TOKEN_ERRORS,
    get_access_token_codec,
    get_password_hasher,
    get_refresh_token_generator,
)
from app.core.throttle import (
    AttemptThrottle,
    get_account_throttle,
    get_caller_throttle,
)
from app.models import User
from app.repositories import RefreshTokenRepository, UserRepository
from app.services import AuthService, UserService

SessionDep = Annotated[Session, Depends(get_session)]

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/access-token")

TokenDep = Annotated[str, Depends(reusable_oauth2)]


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------
def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepositoryDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
def get_auth_service(
    users: UserRepositoryDep, refresh_tokens: RefreshTokenRepositoryDep
) -> AuthService:
    return AuthService(
        users=users,
        refresh_tokens=refresh_tokens,
        password_hasher=get_password_hasher(),
        token_codec=get_access_token_codec(),
        token_generator=get_refresh_token_generator(),
        refresh_token_lifetime_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
    )


def get_user_service(
    users: UserRepositoryDep, refresh_tokens: RefreshTokenRepositoryDep
) -> UserService:
    return UserService(
        users=users,
        refresh_tokens=refresh_tokens,
        password_hasher=get_password_hasher(),
        superuser_email=settings.FIRST_SUPERUSER,
        superuser_password=settings.FIRST_SUPERUSER_PASSWORD,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]


# ---------------------------------------------------------------------------
# Sign-in throttling
# ---------------------------------------------------------------------------
def get_account_throttle_dep() -> AttemptThrottle:
    return get_account_throttle()


def get_caller_throttle_dep() -> AttemptThrottle:
    return get_caller_throttle()


AccountThrottleDep = Annotated[AttemptThrottle, Depends(get_account_throttle_dep)]
CallerThrottleDep = Annotated[AttemptThrottle, Depends(get_caller_throttle_dep)]


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------
def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    """Resolve the caller from a JWT, rejecting anything that fails verification."""
    codec = get_access_token_codec()

    # Signature, algorithm, expiry, issuer, audience and required claims are all
    # checked by the codec. Any forgery or tampering raises from TOKEN_ERRORS.
    try:
        payload = codec.decode(token)
        user_id = uuid.UUID(str(payload["sub"]))
    except TOKEN_ERRORS as exc:
        raise _credentials_error() from exc

    user = session.get(User, user_id)
    if user is None:
        raise _credentials_error()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    # A password change (or logout-everywhere) bumps this, retroactively
    # invalidating tokens that are still cryptographically valid.
    if payload.get("ver") != user.token_version:
        raise _credentials_error()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges",
        )
    return current_user


CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
