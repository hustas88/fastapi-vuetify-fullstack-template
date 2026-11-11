from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.core.config import settings
from app.core.db import get_session
from app.core.throttle import get_account_throttle, get_caller_throttle
from app.main import app

# Never run `create_all` against PostgreSQL during tests, and use a key that is
# long enough for HS256 so PyJWT does not warn.
settings.AUTO_CREATE_SCHEMA = False
settings.SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256"


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless asked, which hides real constraint
    # bugs (e.g. deleting a user that still owns refresh tokens).
    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient]:
    def get_session_override() -> Session:
        return session

    # The throttle is a process-wide singleton; reset it so tests stay isolated.
    get_account_throttle().clear()
    get_caller_throttle().clear()
    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
