from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_exception_handlers
from app.api.main import api_router
from app.core.config import settings
from app.core.db import get_database
from app.core.security import get_password_hasher
from app.repositories import RefreshTokenRepository, UserRepository
from app.services import UserService


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    if settings.AUTO_CREATE_SCHEMA:
        database = get_database()
        database.create_schema()
        with database.session() as session:
            UserService(
                users=UserRepository(session),
                refresh_tokens=RefreshTokenRepository(session),
                password_hasher=get_password_hasher(),
                superuser_email=settings.FIRST_SUPERUSER,
                superuser_password=settings.FIRST_SUPERUSER_PASSWORD,
            ).ensure_superuser()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

install_exception_handlers(app)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Custom headers are invisible to cross-origin JS unless listed. The S3
        # deployment calls the API directly, so without this `X-Total-Count` is
        # unreadable there.
        expose_headers=["X-Total-Count"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", include_in_schema=False)
def root() -> dict[str, dict[str, str]]:
    """Same `{data: ...}` envelope as the versioned API."""
    return {
        "data": {
            "name": settings.PROJECT_NAME,
            "environment": settings.ENVIRONMENT,
            "docs": "/docs",
        }
    }
