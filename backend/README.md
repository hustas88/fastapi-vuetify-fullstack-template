# fastapi-vuetify-fullstack-template — backend

FastAPI + SQLModel + PostgreSQL.

## Commands

Run from the repository root (or `cd backend` and drop the `backend-` prefix):

```bash
make backend-install    # uv sync (creates .venv + uv.lock)
make backend-dev        # uvicorn --reload on :8000
make backend-fmt        # ruff format + ruff check --fix
make backend-lint       # ruff check + format --check
make backend-test       # pytest
make backend-migrate    # alembic upgrade head
```

Interactive docs: <http://localhost:8000/docs>

## Layout

```
app/
  models/               # package: common.py, user.py, auth.py
    common.py           #   IDs, timestamps, Message, error + data/meta envelopes
    user.py             #   users table + UserCreate/UserUpdate/UserPublic
    auth.py             #   token payloads + refresh_tokens table
  repositories/         # UserRepository, RefreshTokenRepository (+ SqlRepository)
  services/             # AuthService, UserService (business rules)
  services/exceptions.py# DomainError subclasses, each carrying its HTTP status
  services/pagination.py# sort allowlist -> ORDER BY clauses
  api/
    deps.py             # dependency wiring (repositories -> services -> routes)
    errors.py           # every failure -> the shared readable JSON envelope
    params.py           # page/per_page/q/sort query-string contract
    main.py             # aggregates all routers
    routes/             # auth, users, health (thin)
  core/
    config.py           # pydantic-settings
    db.py               # Database (engine + session factory)
    email.py            # EmailSender
    security.py         # PasswordHasher, AccessTokenCodec, RefreshTokenGenerator
  main.py               # FastAPI app factory
tests/                  # pytest + TestClient against SQLite
alembic/                # migrations
```

Layering rule: `routes → services → repositories`. Routes never touch a
`Session`, and services never raise `HTTPException`. The underlying database
access (`psycopg`) and email sender (`smtplib`) are synchronous and blocking,
but FastAPI gracefully runs them in a thread pool so the API remains responsive.

Success bodies are wrapped in `data`; collections add paging info in `meta`
(`total_count`, `page`, `per_page`, `total_pages`, `has_next`, `has_previous`).
Errors use `{"error": {...}}` instead, since a failure has no payload.

`AUTO_CREATE_SCHEMA=true` (local default) applies migrations on startup. In
production set it to `false` and run `alembic upgrade head` as a release step
before the new tasks start serving traffic.
