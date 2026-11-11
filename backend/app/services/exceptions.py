"""Domain exceptions.

Each error knows its own HTTP status, so the API layer stays a single generic
handler instead of branching on exception types in every route.
"""

from __future__ import annotations

from fastapi import status


class DomainError(Exception):
    """Base class for expected, client-facing failures."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = "Request could not be completed"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or type(self).detail
        super().__init__(self.detail)


class InvalidCredentialsError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Incorrect email or password"


class InactiveUserError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Inactive user"


class EmailAlreadyExistsError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    detail = "A user with this email already exists"


class InvalidSortFieldError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "That sort field is not supported"


class TooManyLoginAttemptsError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many sign-in attempts. Please wait a moment and try again."


class InvalidRefreshTokenError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Invalid or expired refresh token"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail)


class UserNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "User not found"


class CannotDeleteSelfError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "You cannot delete yourself"


class EmailDeliveryFailedError(DomainError):
    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "Could not send email"
