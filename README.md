# fastapi-vuetify-fullstack-template

Full-stack monorepo skeleton:

| Layer     | Stack                                                                                          |
| --------- | ---------------------------------------------------------------------------------------------- |
| Backend   | Python 3.15 · FastAPI · SQLModel · PostgreSQL 18 · Alembic · **uv** · **ruff** · **pytest**      |
| Frontend  | Node 26 · pnpm 12 · Vue 3.5 · **Vuetify 4** · Vite 8 · TypeScript · vue-router                  |
| Local dev | Docker Compose · Mailpit (SMTP + web inbox, dev only)                                          |
| CI        | GitHub Actions (lint, tests, typecheck, static build) · optional GitLab CI equivalent |

Inspired by [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template).

> **Contributing or using an AI agent?** Read [AGENTS.md](AGENTS.md) first — it
> documents the conventions, commands and invariants that are easy to get wrong.

## Quick start

```bash
make init      # .env.backend / .env.frontend + random SECRET_KEY
make install   # uv sync + pnpm install
make dev       # docker compose up --build (hot reload)
```

| URL                          | Service                         |
| ---------------------------- | ------------------------------- |
| <http://localhost:5173>      | Vue app (Vite dev server)       |
| <http://localhost:8000/docs> | FastAPI Swagger UI              |
| <http://localhost:8000/api/v1/health/> | Health check (ALB probe target) |
| <http://localhost:8025>      | Mailpit — local email inbox (dev stack only) |

The first superuser is seeded from `.env.backend` on startup:
`admin@example.com` / `changethis123` (change these before deploying).

Prefer running the apps on the host? Start only the infrastructure:

```
docker compose up -d db mailpit
make backend-dev    # uvicorn --reload on :8000
make frontend-dev   # vite on :5173
```

## Layout

```
.
├── .github/workflows/          # GitHub Actions: backend.yml, frontend.yml
├── .gitlab-ci.yml              # optional GitLab pipeline, includes ci/*
├── ci/
│   ├── backend.gitlab-ci.yml   # lint, test, docker build/push
│   └── frontend.gitlab-ci.yml  # typecheck + static build artifact
├── backend/
│   ├── app/
│   │   ├── api/                # routers, dependency wiring, error mapping
│   │   ├── core/               # config, db, security, email
│   │   ├── repositories/       # data access (UserRepository, ...)
│   │   ├── services/           # business rules (AuthService, UserService)
│   │   ├── models/             # SQLModel tables + schemas, one module per domain
│   │   └── main.py
│   ├── alembic/                # migrations
│   ├── tests/                  # pytest (SQLite, no DB required)
│   ├── Dockerfile              # dev + runtime targets
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/client.ts       # fetch wrapper + token storage
│   │   ├── composables/        # useAuth()
│   │   ├── layouts/            # PublicLayout (centred) + PrivateLayout (app shell)
│   │   ├── views/              # Dashboard, Login
│   │   ├── router/             # routes, typed meta, guards
│   │   └── App.vue             # picks a layout from `route.meta.layout`
│   ├── Dockerfile              # dev (Vite) + build (static bundle) targets
│   └── package.json
├── .env.backend.example        # API configuration   (copy: .env.backend)
├── .env.frontend.example       # Vite configuration  (copy: .env.frontend)
├── compose.yml                 # deployed-like stack (db, backend — no Mailpit)
├── compose.override.yml        # local dev only: Mailpit + hot reload + Vite
├── Makefile
├── AGENTS.md                   # agent/contributor conventions and invariants
└── pnpm-workspace.yaml
```

## Make targets

Run `make` to list everything.

| Target                              | Description                                         |
| ----------------------------------- | --------------------------------------------------- |
| `make init`                         | Create `.env.*` from the examples, generate a secret |
| `make install`                      | Install backend + frontend dependencies             |
| `make check`                        | Canonical gate: backend lint + tests + frontend typecheck |
| `make dev`                          | Dev stack with hot reload (foreground)              |
| `make up` / `make down` / `make down-v` | Deployed-like stack (db + API) / stop / wipe DB |
| `make logs` / `make ps`             | Inspect the stack                                   |
| `make backend-dev` / `frontend-dev` | Run a single app on the host                        |
| `make backend-fmt` / `backend-lint` | ruff format + check                                 |
| `make backend-test`                 | pytest                                              |
| `make backend-migrate`              | `alembic upgrade head`                              |
| `make backend-revision m="..."`     | Autogenerate a migration                            |
| `make frontend-build`               | Static bundle in `frontend/dist`                    |
| `make frontend-typecheck`           | `vue-tsc --noEmit`                                  |
| `make docker-build`                 | Build the db + API images                           |

## Configuration

Each service is configured by its own file in the repo root, loaded with
Compose's `env_file:` — there are no inline `environment:` blocks to drift from
them. `make init` copies the `*.example` files and randomises
`SECRET_KEY`; the generated files are git-ignored.

| File               | Read by                    | Holds                                              |
| ------------------ | -------------------------- | -------------------------------------------------- |
| `.env.backend`     | `db` + `backend`           | everything the API reads (see below), plus the `POSTGRES_*` credentials |
| `.env.frontend`    | Vite dev server            | `VITE_API_URL`, `VITE_PROXY_TARGET`                |

The most relevant backend keys:

| Variable                  | Default                          | Notes                                              |
| ------------------------- | -------------------------------- | -------------------------------------------------- |
| `SECRET_KEY`              | `changethis`                     | JWT signing key — **must** be ≥32 chars outside `local` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15`                         | Access-token lifetime                              |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `fastapi-vuetify-fullstack-template` / `…-web` | Claims embedded in and verified against every token |
| `DATABASE_URL`            | `postgresql+psycopg://…@db/app`  | Interpolated from the `POSTGRES_*` values          |
| `AUTO_CREATE_SCHEMA`      | `true`                           | Runs `alembic upgrade head` + seeds the superuser on startup |
| `FIRST_SUPERUSER*`        | `admin@example.com` / `…`        | Initial login                                      |
| `BACKEND_CORS_ORIGINS`    | `localhost:5173,localhost:8080`  | Comma separated list of browser origins            |
| `EMAIL_PROVIDER`          | `smtp`                           | `smtp` (Mailpit locally) or `ses` (deployed)        |
| `SMTP_HOST` / `SMTP_PORT` | `mailpit` / `1025`               | Generic relay used when `EMAIL_PROVIDER=smtp`       |
| `SES_REGION` + `SES_SMTP_*` | `us-east-1` / empty            | SES SMTP credentials (not AWS keys); host derived from region |

Running an app on the host instead of Compose? The backend falls back to the
defaults in `app/core/config.py` (Mailpit on `localhost:1025`), so
`make backend-dev` works without `.env.backend`.

## Database migrations

Local development runs with `AUTO_CREATE_SCHEMA=true`, which applies migrations
(not `create_all`, so `alembic_version` stays in sync) and seeds the superuser.
For managed environments:

```bash
# 1. point DATABASE_URL at the target database
# 2. set AUTO_CREATE_SCHEMA=false
make backend-revision m="create users"
make backend-migrate
```

The image runs migrations only through `AUTO_CREATE_SCHEMA` (local) — it has no
built-in migrate-then-start entrypoint. A deployed environment runs
`alembic upgrade head` once as a release step, before the new tasks take
traffic.

`alembic/versions/` holds a single baseline revision (`04c9660d5f43`, both
tables). The pre-release history was squashed, so a database created before that
squash must be recreated (`make down-v`) or stamped:

```bash
make backend-migrate                                    # apply the baseline
# or, for a database that already has the schema:
docker compose run --rm backend alembic stamp head
```

## CI

### GitHub Actions (default)

`.github/workflows/` runs on every push to `main` and on pull requests, filtered
by path so an unrelated change does not rebuild everything:

- **Backend** (`backend.yml`) — `ruff check`, `ruff format --check`, `pytest`.
  Toolchain versions match the Dockerfile (`uv 0.13.7`, Python 3.15); the test
  suite uses SQLite in memory, so no database service is needed.
- **Frontend** (`frontend.yml`) — `pnpm install --frozen-lockfile`,
  `vue-tsc --noEmit`, `vite build`, then a check that no dev-only strings
  (`mailpit`) reached `frontend/dist`. The bundle is uploaded as an artifact.

This is the same set of checks `make check` runs locally.

### GitLab CI (optional)

`.gitlab-ci.yml` is the global file; it includes `ci/backend.gitlab-ci.yml` and
`ci/frontend.gitlab-ci.yml`. Stages: `test` → `build` → `deploy`.

**Trigger any combination** from *Run pipeline* (or the API):

| Goal          | Variables                                 |
| ------------- | ----------------------------------------- |
| Both          | `BUILD_ALL=true`                          |
| Backend only  | `BUILD_BACKEND=true` `BUILD_FRONTEND=false` |
| Frontend only | `BUILD_FRONTEND=true` `BUILD_BACKEND=false` |
| Skip a part   | `BUILD_BACKEND=false` / `BUILD_FRONTEND=false` |

If no variables are set, GitLab detects changes from the diff
(`backend/**`, `frontend/**`, manifests, CI files). When nothing matches, the
jobs appear as **manual** actions instead of being skipped silently.

Jobs:

- `backend:lint` — `ruff check` + `ruff format --check`
- `backend:test` — `alembic upgrade head` against a PostgreSQL service + `pytest`
- `backend:docker` — multi-stage image pushed to `$CI_REGISTRY_IMAGE/backend`
  (`:<sha>`, `:latest` on the default branch, `:<tag>` on tags)
- `frontend:build` — `vue-tsc` + `vite build`, artifact `frontend/dist`

Deployment is deliberately left out: the `deploy` stage contains commented
examples for syncing `frontend/dist` to S3 and for deploying the backend image.

## Container images

Every image is either a Docker Official Image or the official upstream image
published by the project itself:

| Image | Used by | Notes |
| ----- | ------- | ----- |
| `postgres:18-alpine` | Compose, CI service | Docker Official Image |
| `python:3.15-slim` | Backend Dockerfile, CI | Docker Official Image |
| `node:26-alpine` | Frontend Dockerfile, CI | Docker Official Image |
| `docker:28-cli` / `docker:28-dind` | CI docker build job | Docker Official Image |
| `ghcr.io/astral-sh/uv:0.13.7` | Backend build (uv binary) | Official image published by Astral |
| `axllent/mailpit:v1` | Local dev only (`compose.override.yml`) | Official Mailpit image (no Docker Official Image exists) |

Version pins live in the Dockerfiles as build args so they are easy to bump:

```bash
# backend/Dockerfile
ARG PYTHON_VERSION=3.15
ARG UV_VERSION=0.13.7

# frontend/Dockerfile
ARG NODE_VERSION=26
ARG PNPM_VERSION=12.18.0
```

Override at build time without editing files:

```bash
docker build --build-arg UV_VERSION=0.14.0 -f backend/Dockerfile .
```

For fully reproducible deployments, resolve the tags to digests
(`docker buildx imagetools inspect <image>`), e.g.
`FROM python:3.15-slim@sha256:<digest>`.

## Authentication and tokens

The API uses **short-lived access tokens plus rotating refresh tokens**, so an
active session is never interrupted but an idle one expires.

| Token | Form | Lifetime | Stored |
| ----- | ---- | -------- | ------ |
| Access | HS256 JWT | `ACCESS_TOKEN_EXPIRE_MINUTES` (15 min) | `localStorage` |
| Refresh | opaque random string | `REFRESH_TOKEN_EXPIRE_DAYS` (30 days, sliding) | `localStorage` |

- `POST /api/v1/auth/register` creates an account (the only unauthenticated
  write endpoint) and returns `201` with a `Location` header pointing at
  `/api/v1/users/{id}`.
- `POST /api/v1/auth/access-token` returns both tokens and `expires_in`.
- `POST /api/v1/auth/refresh-token` exchanges a refresh token for a new pair.
- `POST /api/v1/auth/logout` revokes the current session chain.

Everything under `/api/v1/auth` is unauthenticated; everything under
`/api/v1/users` requires a token (`/me` for the caller, the collection and
`DELETE` for superusers).

The refresh token is **opaque, not a JWT**: it must be revocable, and
revocation requires a database lookup. Only its SHA-256 digest is stored, so a
database leak does not yield usable credentials.

**Rotation:** every refresh consumes the presented token and issues a new one
in the same *family*. Consumption is a single conditional `UPDATE`, so two
concurrent refreshes of the same token cannot both succeed. Presenting an
already-rotated token is treated as theft and revokes the whole family — which
logs out only that device chain, not other sessions.

**Idle window:** each refresh slides `expires_at` forward, so a user who keeps
using the app never gets logged out. Stop using it for `REFRESH_TOKEN_EXPIRE_DAYS`
and renewal fails, requiring a fresh login. The frontend refreshes
transparently: a `401` triggers a single shared refresh call and one retry,
so concurrent requests cannot race each other into a revoked token.

Access-token hardening in place:

- **Only `HS256` is accepted.** The algorithm allowlist prevents `alg: none`
  and algorithm-confusion attacks.
- **Every claim is required and verified**: `exp`, `iat`, `sub` (the user's
  UUID), `iss`, `aud`, `jti`, `ver`. Missing or mismatched claims are rejected.
- **Short signing keys are refused.** A `SECRET_KEY` shorter than 32
  characters makes the API fail at startup unless `ENVIRONMENT=local`.
  Generate one with `openssl rand -hex 32`.
- **Tokens are revocable.** Password changes bump `token_version` (killing
  access tokens) and revoke every stored refresh token.
- **Login timing is equalized** so response time does not reveal whether an
  email exists.

The browser stores the token in `localStorage`, which is simple but readable by
any injected script. If you need stronger XSS isolation, switch to short-lived
access tokens in an `httpOnly` cookie plus CSRF protection — that requires a
same-origin proxy or `SameSite=None; Secure` cookies across the S3/API split.

`tests/test_auth_security.py` attempts forgery (wrong key, `alg: none`, tampered
payload, wrong audience/issuer, missing claims) and
`tests/test_refresh_tokens.py` covers rotation, replay detection, expiry,
logout and password-change revocation.

## Response format

Success bodies are always wrapped in `data`, so the payload is in the same
place for every endpoint:

```json
{ "data": { "message": "ok" } }
```

Collections put their paging summary in `meta` (the JSON:API arrangement, which
leaves room for `links` later):

```json
{
  "data": [{ "id": "…", "email": "a@example.com" }],
  "meta": {
    "total_count": 57, "page": 2, "per_page": 25,
    "total_pages": 3, "has_next": true, "has_previous": true
  }
}
```

`GET /api/v1/users/` is the reference implementation and every future grid uses
the same query contract:

```
?page=2&per_page=25&q=acme&sort=-created_at,email
```

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `page` | `1` | 1-based |
| `per_page` | `25` | capped at `100` |
| `q` | — | case-insensitive search over the resource's searchable columns |
| `sort` | `-created_at` | comma separated allowlist (max 5 fields); `-` prefix = descending |

`total_count` is also sent as an `X-Total-Count` header (exposed through CORS
for the S3 deployment). An unknown `sort` field is rejected with `400` rather
than silently ignored, and `204` responses stay body-less.

## Error format

Every failure — validation, authentication, routing or a crash — returns the
same human-readable envelope, so a client never sees Pydantic's internal error
list:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Password: Must be at least 8 characters long.",
    "details": [{ "field": "password", "message": "Must be at least 8 characters long." }]
  }
}
```

| Status | `code` examples | `message` |
| ------ | --------------- | --------- |
| 422 | `validation_error` | `Field: reason`, or a summary plus per-field `details` |
| 401 | `unauthorized` / `invalid_refresh_token` | `Sign in to continue.` |
| 404 | `not_found` / `user_not_found` | `The requested resource could not be found.` |
| 405 | `method_not_allowed` | `This endpoint does not accept that HTTP method.` |
| 409 | `email_already_exists` | `A user with this email already exists.` |
| 500 | `internal_error` | `Something went wrong on our end. Please try again.` |

`code` is stable and safe to branch on; `message` is prose; `details` only
appears when specific fields are at fault. Internals (`type`, `loc`, `input`,
`ctx`) never reach the client, and unhandled exceptions are logged server-side
instead of leaking a traceback. `backend/tests/test_errors.py` pins the format.

## Production notes

- **Frontend (S3 static website):** build with an absolute API origin, e.g.
  `VITE_API_URL=https://api.example.com/api/v1 make frontend-build`, then
  upload `frontend/dist`. Configure the bucket's 403/404 fallback to
  `index.html` so client-side routing works, and allow the site origin in
  `BACKEND_CORS_ORIGINS`.
- **Database:** use a fresh PostgreSQL instance, set
  `AUTO_CREATE_SCHEMA=false` in production, and run `alembic upgrade head` once
  as a release step before the new tasks take traffic.
- **Runtime (AWS ALB):** the image contains no `HEALTHCHECK` — point the target
  group at `/api/v1/health/`. Set `FORWARDED_ALLOW_IPS` to the
  ALB/VPC CIDRs so `X-Forwarded-For`/`-Proto` are trusted (otherwise uvicorn
  ignores them and every client looks like the ALB).
- **Secrets:** rotate `SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD` and the
  database password. Do not commit `.env.backend` or `.env.frontend` — only the
  `*.example` files belong in git.
- **Email:** deployed environments send through Amazon SES. Set
  `EMAIL_PROVIDER=ses`, `SES_REGION`, `SES_SMTP_USERNAME` and
  `SES_SMTP_PASSWORD` (IAM SES SMTP credentials with `ses:SendRawEmail` — not
  the AWS access/secret key), and make `EMAILS_FROM_EMAIL` a verified identity
  in that region. Mailpit is **not** part of `compose.yml` — it only runs
  locally via `compose.override.yml`, so the deployed backend can never fall
  back to a local inbox. Missing SES settings do not stop the API from booting;
  sending fails with a clear error instead.

## Lockfiles

`backend/uv.lock` and `pnpm-lock.yaml` are committed, and Docker/CI install with
`--frozen-lockfile`/`uv sync` so builds are reproducible. After changing
dependencies:

```bash
make backend-lock    # regenerate backend/uv.lock
make frontend-install # regenerate pnpm-lock.yaml
```

## What has been verified

- Backend: `ruff` clean, `ruff format --check` clean, the full `pytest` suite
  passes (SQLite in-memory, no database required).
- Database: `alembic upgrade head` applies on PostgreSQL 18 and
  `alembic check` reports no model drift.
- Frontend: `vue-tsc --noEmit` passes and `vite build` emits `frontend/dist`,
  the artifact that is uploaded to the S3 bucket website.
- Compose (deployed-like): only `db` + `backend`, both configured by
  `env_file:`, and the seeded superuser can log in and read/update their
  account.
- Compose (dev): Vite dev server proxies `/api` to the reloading backend, and
  Mailpit runs alongside the stack.

