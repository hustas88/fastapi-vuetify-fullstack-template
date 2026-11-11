from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import EmailStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# HS256 keys should be at least as long as the hash output (32 bytes).
MIN_SECRET_KEY_LENGTH = 32

# Values shipped in the example files. Copying one unchanged into a deployed
# environment is a configuration mistake worth failing on.
PLACEHOLDER_SECRETS = {"changethis"}
PLACEHOLDER_PASSWORDS = {"changethis", "changethis123", "changeme", "password", "secret"}


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # General
    PROJECT_NAME: str = "fastapi-vuetify-fullstack-template"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "changethis"
    # Access tokens are short-lived because refresh tokens carry the session.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    # Idle window for a session: every refresh slides this forward, so an active
    # user is never logged out, but an idle one expires after this many days.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # Tokens carry these claims and are validated against them.
    JWT_ISSUER: str = "fastapi-vuetify-fullstack-template"
    JWT_AUDIENCE: str = "fastapi-vuetify-fullstack-template-web"
    # `NoDecode` disables pydantic-settings' JSON parsing so the comma separated
    # form (`a,b,c`) reaches the validator below untouched.
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/app"
    AUTO_CREATE_SCHEMA: bool = True

    # Seeded on startup when AUTO_CREATE_SCHEMA is enabled
    FIRST_SUPERUSER: EmailStr | None = None
    FIRST_SUPERUSER_PASSWORD: str | None = None

    # Email
    # "smtp" = any SMTP relay (Mailpit locally); "ses" = Amazon SES via SMTP.
    EMAIL_PROVIDER: Literal["smtp", "ses"] = "smtp"
    EMAILS_FROM_EMAIL: str = "noreply@example.com"
    EMAILS_FROM_NAME: str | None = None

    SMTP_HOST: str | None = "localhost"
    SMTP_PORT: int = 1025
    SMTP_TLS: bool = False
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None

    # SES SMTP credentials (not the AWS secret access key). The relay host is
    # derived from the region; the from-address must be a verified identity.
    SES_REGION: str = "us-east-1"
    SES_SMTP_USERNAME: str | None = None
    SES_SMTP_PASSWORD: str | None = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Accept either a JSON list or a comma separated string."""
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value  # type: ignore[return-value]

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_token_lifetime(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        return value

    @field_validator("REFRESH_TOKEN_EXPIRE_DAYS")
    @classmethod
    def validate_refresh_lifetime(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be positive")
        return value

    @model_validator(mode="after")
    def validate_secret_key(self) -> Settings:
        """Refuse to start with a short signing key outside local development.

        A guessable SECRET_KEY lets anyone forge valid tokens for any user, so
        this is a hard failure in staging/production and a loud warning locally.
        RFC 7518 §3.2 requires an HS256 key of at least 256 bits (32 bytes).
        """
        if len(self.SECRET_KEY.strip()) >= MIN_SECRET_KEY_LENGTH:
            return self

        detail = (
            f"SECRET_KEY is insecure because it is shorter than "
            f"{MIN_SECRET_KEY_LENGTH} characters. "
            "Generate one with `openssl rand -hex 32`."
        )
        if self.ENVIRONMENT == "local":
            warnings.warn(f"{detail} Allowed only because ENVIRONMENT=local.", stacklevel=2)
            return self
        raise ValueError(detail)

    @model_validator(mode="after")
    def validate_deployment_defaults(self) -> Settings:
        """Refuse example credentials outside local development.

        The shipped env files are meant to be edited. A deployed API that still
        carries `changethis123` as the seeded superuser password is trivially
        compromised, so it must not boot.
        """
        if self.ENVIRONMENT == "local":
            return self

        problems: list[str] = []
        if self.SECRET_KEY.strip().lower() in PLACEHOLDER_SECRETS:
            problems.append("SECRET_KEY is still the example value")
        password = (self.FIRST_SUPERUSER_PASSWORD or "").strip().lower()
        if password in PLACEHOLDER_PASSWORDS:
            problems.append("FIRST_SUPERUSER_PASSWORD is still the example value")
        if problems:
            raise ValueError("; ".join(problems) + ". Update the env file before deploying.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
