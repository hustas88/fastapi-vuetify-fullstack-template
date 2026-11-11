"""One place that turns exceptions into readable JSON errors.

Every error the API returns uses the same envelope, so a client never has to
understand FastAPI or Pydantic internals:

    {
      "error": {
        "code": "validation_error",
        "message": "Password: Must be at least 8 characters long.",
        "details": [
          {"field": "password", "message": "Must be at least 8 characters long."}
        ]
      }
    }

`code` is stable and meant for programs; `message` is a sentence meant for
people; `details` is present only when individual fields are at fault.
"""

from __future__ import annotations

import http
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.exceptions import DomainError

logger = logging.getLogger(__name__)

# Matches the sign-in throttle window (`app/core/throttle.py`).
THROTTLE_RETRY_AFTER_SECONDS = 60

# `loc` starts with where the value came from; that prefix is noise to a reader.
_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}

# Pydantic prefixes messages raised by custom validators; the prefix is not
# something a user should see.
_MESSAGE_PREFIXES = ("Value error, ", "Assertion failed, ")

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}

# Used when an HTTPException carries only the standard status phrase.
_HTTP_MESSAGES = {
    400: "The request could not be understood.",
    401: "Sign in to continue.",
    403: "You do not have permission to do that.",
    404: "The requested resource could not be found.",
    405: "This endpoint does not accept that HTTP method.",
    409: "The request conflicts with the current state of the resource.",
    413: "The request is too large.",
    415: "That content type is not supported.",
    429: "Too many requests. Please slow down and try again.",
    500: "Something went wrong on our end. Please try again.",
    502: "A service we depend on is unavailable. Please try again.",
    503: "The service is temporarily unavailable. Please try again later.",
}


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def _sentence(text: str) -> str:
    """Trim and punctuate a message so it reads as a standalone sentence."""
    for prefix in _MESSAGE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.strip().rstrip(".")
    if not text:
        return ""
    return f"{text[0].upper()}{text[1:]}."


def _snake_case(name: str) -> str:
    """`EmailAlreadyExistsError` -> `email_already_exists`."""
    joined = "".join(f"_{char.lower()}" if char.isupper() else char for char in name)
    return joined.lstrip("_")


def _format_value(value: object) -> str:
    """Render a Pydantic `ctx` value for a sentence (lists read better joined)."""
    if isinstance(value, list | tuple | set | frozenset):
        return ", ".join(str(item) for item in value)
    return str(value)


def _field_name(location: Sequence[object]) -> str:
    """`("body", "items", 0, "name")` -> `items[0].name`."""
    name = ""
    for part in location:
        text = str(part)
        if text in _LOCATION_PREFIXES:
            continue
        if text.isdigit():
            name += f"[{text}]"
        elif name:
            name += f".{text}"
        else:
            name = text
    return name


def _field_label(field: str) -> str:
    """`full_name` -> `Full name`, for use at the start of a sentence."""
    label = field.replace("_", " ").replace(".", " ").strip()
    return f"{label[0].upper()}{label[1:]}" if label else ""


# ---------------------------------------------------------------------------
# Validation errors (the ugly ones by default)
# ---------------------------------------------------------------------------
def _describe(error: dict[str, Any]) -> str:
    """Turn one Pydantic error into a sentence a person can act on."""
    kind = str(error.get("type", ""))
    ctx = error.get("ctx") or {}

    # Pydantic wraps email/regex failures as "value is not a valid X: <reason>";
    # the reason on its own reads better.
    reason = ctx.get("reason")
    if isinstance(reason, str) and reason.strip():
        return _sentence(reason)

    if kind == "missing":
        return "This field is required."
    if kind == "string_too_short":
        return f"Must be at least {ctx.get('min_length')} characters long."
    if kind == "string_too_long":
        return f"Must be at most {ctx.get('max_length')} characters long."
    if kind == "string_type":
        return "Must be text."
    if kind == "string_pattern_mismatch":
        return "Does not match the required format."
    if kind in {"int_type", "int_parsing"}:
        return "Must be a whole number."
    if kind in {"float_type", "float_parsing", "decimal_type", "decimal_parsing"}:
        return "Must be a number."
    if kind in {"bool_type", "bool_parsing"}:
        return "Must be true or false."
    if kind == "greater_than":
        return f"Must be greater than {ctx.get('gt')}."
    if kind == "greater_than_equal":
        return f"Must be {ctx.get('ge')} or greater."
    if kind == "less_than":
        return f"Must be less than {ctx.get('lt')}."
    if kind == "less_than_equal":
        return f"Must be {ctx.get('le')} or lower."
    if kind in {"list_type", "tuple_type", "set_type", "frozen_set_type"}:
        return "Must be a list."
    if kind in {"dict_type", "model_attributes_type"}:
        return "Must be an object."
    if kind in {"uuid_type", "uuid_parsing", "uuid_version"}:
        return "Must be a valid identifier."
    if kind in {"date_type", "date_parsing", "date_from_datetime_parsing"}:
        return "Must be a valid date."
    if kind in {"datetime_type", "datetime_parsing", "datetime_from_date_parsing"}:
        return "Must be a valid date and time."
    if kind == "time_type" or kind.startswith("time_"):
        return "Must be a valid time."
    if kind == "json_invalid":
        return "The request body is not valid JSON."
    if kind in {"literal_error", "enum"} and "expected" in ctx:
        return f"Must be one of: {_format_value(ctx['expected'])}."
    if kind == "extra_forbidden":
        return "This field is not allowed."

    # Anything else (EmailStr, custom validators, rare Pydantic codes) already
    # carries a readable sentence in `msg`.
    return _sentence(str(error.get("msg", ""))) or "Invalid value."


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Report which fields are wrong, and why, in plain language."""
    details = [_describe_error(error) for error in exc.errors()]

    if len(details) == 1:
        field, reason = details[0]["field"], details[0]["message"]
        message = f"{_field_label(field)}: {reason}" if field else reason
    else:
        message = "Some of the submitted values are invalid."

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_body(
            code=_HTTP_CODES[422],
            message=message,
            details=details,
        ),
    )


def _describe_error(error: dict[str, Any]) -> dict[str, str]:
    """One Pydantic error as `{field, message}`, with no internals."""
    # A malformed body is about the request as a whole, not a field: its `loc`
    # is just the (unnamed) root, e.g. `("body", 0)`.
    field = "" if error.get("type") == "json_invalid" else _field_name(error.get("loc", ()))
    return {"field": field, "message": _describe(error)}


# ---------------------------------------------------------------------------
# Domain and HTTP errors
# ---------------------------------------------------------------------------
def _body(
    *,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return {"error": payload}


def _status_phrase(code: int) -> str:
    try:
        return http.HTTPStatus(code).phrase
    except ValueError:
        return ""


def _http_message(exc: StarletteHTTPException) -> str:
    """Prefer a deliberate `detail`; fall back to friendly text per status."""
    detail = exc.detail if isinstance(exc.detail, str) else ""
    if not detail or detail == _status_phrase(exc.status_code):
        fallback = _HTTP_MESSAGES.get(exc.status_code)
        return fallback or f"The request could not be completed ({exc.status_code})."
    return _sentence(detail)


async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Expected, client-facing failures. The class name becomes the code."""
    headers: dict[str, str] = {}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    elif exc.status_code == 429:
        # Tell well-behaved clients how long to back off.
        headers["Retry-After"] = str(THROTTLE_RETRY_AFTER_SECONDS)
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(code=_domain_code(exc), message=_sentence(exc.detail)),
        headers=headers or None,
    )


def _domain_code(exc: DomainError) -> str:
    name = type(exc).__name__.removesuffix("Error")
    if name == "Domain":  # the base class was raised directly
        return _HTTP_CODES.get(exc.status_code, "error")
    return _snake_case(name)


async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Starlette/FastAPI `HTTPException`, including routing 404s and 405s."""
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(
            code=_HTTP_CODES.get(exc.status_code, "error"),
            message=_http_message(exc),
        ),
        headers=getattr(exc, "headers", None),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: never leak a traceback or internal message to a client."""
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_body(code=_HTTP_CODES[500], message=_HTTP_MESSAGES[500]),
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]
