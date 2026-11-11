"""Database access, encapsulated in a `Database` object."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session, create_engine

from app.core.config import settings

# `backend/`, wherever the app is installed or mounted from.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Database:
    """Owns the engine and hands out sessions.

    Sessions are caller-owned: repositories commit but never close them.
    """

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self._url = url
        # `pool_pre_ping` keeps connections healthy across database restarts.
        self.engine = create_engine(url, pool_pre_ping=True, echo=echo)

    @contextmanager
    def session(self) -> Generator[Session]:
        """Open a session that is closed on exit."""
        with Session(self.engine) as session:
            yield session

    def create_schema(self) -> None:
        """Bring the database to the latest revision on startup.

        Migrations rather than `SQLModel.metadata.create_all`: `create_all`
        leaves no `alembic_version` row, so a database created that way can no
        longer be migrated (the first real migration would fail with
        "relation already exists"). Running `upgrade head` is idempotent and
        keeps the two paths consistent.
        """
        from alembic import command
        from alembic.config import Config

        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        # `alembic.ini` uses relative paths; anchor them at the backend root so
        # this works regardless of the process working directory.
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", self._url.replace("%", "%%"))
        command.upgrade(config, "head")


@lru_cache
def get_database() -> Database:
    return Database(str(settings.DATABASE_URL))


def get_session() -> Generator[Session]:
    """FastAPI dependency yielding a session from the default database."""
    with get_database().session() as session:
        yield session
