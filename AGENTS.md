# AGENTS.md

Instructions for AI coding agents (and humans) working in this repository.
Read this before changing code. It documents conventions that are **not**
obvious from the file tree, and invariants that will break the build if you
violate them.

## What this repo is

A pnpm monorepo skeleton with two independently deployed apps:

| App          | Path        | Stack                                                                     |
| ------------ | ----------- | ------------------------------------------------------------------------- |
| API          | `backend/`  | Python 3.15 · FastAPI · SQLModel · Alembic · PostgreSQL 18 · uv · ruff · pytest (runs sync/blocking I/O in thread pool) |
| Web          | `frontend/` | Vue 3.5 · Vuetify 4 · Vite 8 · TypeScript · vue-router                     |

Deployment targets differ: the frontend is a **static S3 site**, the backend is
a **container**. Because of that, the frontend must never assume same-origin;
it talks to `VITE_API_URL` and the API must allow the site origin via CORS.

Local development is Docker Compose. Production is **not** Docker Compose —
`compose.yml` exists to reproduce the deployed topology locally.

## Repository layout

```
.gitlab-ci.yml            Global pipeline; includes ci/*.yml
ci/backend.gitlab-ci.yml  lint, test, docker build/push
ci/frontend.gitlab-ci.yml typecheck + static build artifact
backend/
  app/api/                routers (routes/) + shared dependencies (deps.py)
  app/core/               config.py, db.py, security.py, email.py
  app/models/             package: common.py, user.py, auth.py (one module per aggregate)
  app/repositories/       data access (one class per aggregate)
  app/services/           business rules (AuthService, UserService)
  app/main.py             app factory, CORS, lifespan
  alembic/                migrations (env.py imports app.models)
  tests/                  pytest, SQLite in-memory, no database needed
frontend/
  src/api/client.ts       fetch wrapper, token storage, typed endpoints
  src/composables/        useAuth()
  src/router/index.ts     routes + auth guard
  src/views/              Dashboard, Login
  src/components/         DevTools*.vue (dev-only, see below)
compose.yml               deployed topology (db, backend, frontend)
compose.override.yml      local dev only (adds Mailpit, hot reload, Vite)
.agents/skills/           vendored agent skills (see Agent skills)
```

## Commands

**Always drive the project through `make`.** The Makefile is the single source
of truth for how this repo is built, tested and run; it already knows the right
working directory, `uv`/`pnpm` flags, Docker targets and ports. Do not invent
raw `uv run …`, `pnpm …` or `docker compose …` invocations unless a `make`
target is missing — and if one is missing, prefer adding it to the `Makefile`
over baking a one-off command into your workflow. Agents run with a different
shell and environment than a human: `make` is what makes those paths safe.

Run `make` (no args) to list every target with a description.

### After you change code: run this

Pick the row that matches what you touched and run **all** of its commands.

| You changed | Run | Notes |
| ----------- | --- | ----- |
| Anything at all | `make check` | Canonical gate: backend lint + tests + frontend typecheck, each run exactly once |
| `backend/app/**` or `backend/tests/**` | `make backend-lint backend-test` | `make backend-fmt` first if formatting complaints appear |
| `frontend/src/**`, `frontend/*.ts`, `frontend/*.json` | `make frontend-typecheck` | A type error fails `make frontend-build` |
| A SQLModel table in `app/models/` | `make backend-revision m="add x"` → edit the file → `make backend-migrate` | Also run `alembic check`; see *Adding a table* |
| `backend/alembic/**` | `make backend-migrate` | Then `make check` |
| `compose.yml` / `compose.override.yml` | `docker compose config --services` and `docker compose -f compose.yml config --services` | Expect `db, mailpit, backend, frontend` and `db, backend` — see *Environment* |
| `backend/pyproject.toml` | `make backend-install`, then `make backend-lock` | Commit `backend/uv.lock` |
| `frontend/package.json`, `pnpm-workspace.yaml` | `make frontend-install` | Commit `pnpm-lock.yaml` |
| `.env.*.example` | Mirror the key in `app/core/config.py` + docs | Never commit the generated `.env.*` |
| `frontend/src/components/DevTools*.vue` | `make frontend-build` | Then grep `frontend/dist` for `mailpit` — must be 0 |
| `ci/**`, `.gitlab-ci.yml`, `.github/workflows/**` | Nothing local; re-read *Invariants* | Jobs must stay green with and without `BUILD_*` flags |
| Dockerfiles | `make docker-build` | Confirm pinned `ARG` values still resolve |

`make dev` / `make up` are for manual inspection only — do not leave the stack
running at the end of a task. Tear down with `make down-v` (deletes the
database volume) or `make down`.

### Target reference

```bash
make init        # create .env.backend/.env.frontend, random SECRET_KEY
make install     # uv sync + pnpm install
make check       # backend lint + backend tests + frontend typecheck (the gate)

make dev         # dev stack, foreground (Mailpit + Vite + uvicorn --reload)
make up          # deployed topology in the background (db + API, no Mailpit)
make down / down-v / logs / ps

make backend-lint / backend-fmt / backend-test / backend-migrate / backend-dev
make backend-revision m="add x" / backend-lock / backend-install
make frontend-typecheck / frontend-build / frontend-dev / frontend-install
make docker-build
```

If `uv` or `node` are not installed locally, the same checks run in Docker —
prefer this when `make` reports a missing toolchain. The Makefile already
detects this: a missing `uv`/`pnpm` prints a red notice with the exact Docker
command to run and exits non-zero. That is **guidance, not a code failure** —
do not report it as a test failure, and do not "fix" it by installing toolchains
into the repo.

```bash
docker build --target dev -t fastapi-vuetify-backend-dev -f backend/Dockerfile .
docker run --rm fastapi-vuetify-backend-dev sh -c "cd /app && uv run ruff check . && uv run ruff format --check . && uv run pytest -q"

docker build --target build -t fastapi-vuetify-frontend-build -f frontend/Dockerfile .
docker run --rm fastapi-vuetify-frontend-build sh -c "cd /app && pnpm --filter @app/frontend typecheck"
```

**A change is not done until `make check` passes** (or its Docker equivalent
above). `make check` runs backend lint, backend tests and the frontend
typecheck exactly once each, so it is the only verification target. For anything
touching migrations, also run `uv run alembic check` (expects "No new upgrade
operations detected"). Report the exact commands you ran and their outcome in
your final message — do not claim success without having run them.

## Backend conventions

### Architecture: layered, object-oriented

The backend is split into four layers. Dependencies point **inward only** — a
router never touches a session, and a service never imports HTTP.

```
app/
  models/              package: common.py (shared), user.py, auth.py
                       entities + API schemas (behaviour on entities)
  repositories/        UserRepository, RefreshTokenRepository   (data access)
  services/            AuthService, UserService                (business rules)
  api/                 deps.py (wiring), errors.py (mapping), routes/ (thin)
  core/                config, db (Database), security (codecs), email
```

| Layer | May import | Must not |
| ----- | ---------- | -------- |
| `repositories` | models, `sqlmodel` | services, FastAPI |
| `services` | repositories, `core/security` objects (PasswordHasher, ...), models | FastAPI, `HTTPException` |
| `api/routes` | deps, models, services | `Session`, SQL, repositories |
| `core` | settings only | anything above it |

Rules that keep this honest:

- **Routes stay thin** — parse input, call one service method, return. If a
  route has an `if`, the rule belongs in the service.
- **No `HTTPException` in services.** Raise a `DomainError` subclass from
  `services/exceptions.py`; `api/errors.py` maps it to a response using the
  exception's own `status_code`. Adding an error means adding a subclass, not
  editing a route.
- **Every error response uses one envelope** (see *Error format* below).
  `api/errors.py` owns the shape: domain errors, validation errors and
  `HTTPException`s all go through it, so never build a `JSONResponse` with an
  ad-hoc error body in a route.
- **Repositories own the session, services own the rules.** Repositories commit
  and return entities; they never decide *whether* something may happen.
- **Extend `SqlRepository` for new repositories.** `app/repositories/base.py`
  provides `save(entity)` (insert *or* update + refresh), `delete(entity)` and
  `_commit_all(entities)`. Do not re-implement `session.add`/`commit`/`refresh`
  in a subclass; an `add(...)` method should build the entity and delegate to
  `save`.
- **No `Protocol`/`ABC` layer over repositories.** With a single implementation
  each and no static type checker configured, an interface would be unenforced
  ceremony. The seam that matters is constructor injection: services accept
  repositories by argument and only rely on method names, so a fake already
  works without inheritance. Introduce a `Protocol` only when a second
  implementation appears, tests start using fakes, or mypy/pyright is added.
- **Behaviour on entities.** Small state transitions live on the model (e.g.
  `RefreshToken.revoke()`, `RefreshToken.is_expired()`, `User.record_credential_change()`)
  rather than as helpers that mutate from outside.
- **Inject collaborators.** Services take their repositories and security
  objects as constructor arguments; `api/deps.py` builds them per request. This
  is what makes them testable with fakes — no module-level singletons inside a
  service.

### Adding an endpoint

1. Define/extend schemas and tables in `app/models/<domain>.py` (`XBase` →
   `X` table → `XCreate`/`XUpdate`/`XPublic`), then re-export it from
   `app/models/__init__.py` so the table is registered on `SQLModel.metadata`
   and the `from app.models import X` import keeps working.
2. Add the rule to a service (`app/services/*.py`). If it needs new queries, add
   repository methods first.
3. Expose it in `app/api/routes/<resource>.py` using the injected service:
   ```python
   from app.api.deps import CurrentUser, UserServiceDep

   @router.post("/things", response_model=ThingPublic)
   def create_thing(service: ThingServiceDep, current_user: CurrentUser, body: ThingCreate):
       return service.create(body, owner=current_user)
   ```
4. Register the router in `app/api/main.py`. The `/api/v1` prefix is applied
   there, so **never** hardcode `/api/v1` inside a router.

### Schema conventions

- **Table names are plural**: `users`, not `user`. Set `__tablename__`
  explicitly on every `table=True` model.
- **`id` is always the first column** and is a `uuid.UUID` created by
  `new_id()` (UUIDv7 — time-ordered, so inserts keep index locality). To use
  random v4 instead, swap `uuid.uuid7()` for `uuid.uuid4()` in `new_id()`.
- **Declare table columns explicitly instead of inheriting from `XBase`.**
  SQLAlchemy emits inherited columns first, which puts `id` *after* the base
  fields. `UserBase` is therefore only a base for the API schemas
  (`UserCreate`/`UserPublic`), not for the table.
- `password` on the table stores an **Argon2 hash**, never plaintext. Hashing
  happens in `UserService` via `PasswordHasher`.
- **Timestamps carry DB defaults** (`server_default=now()`), so inserts that
  bypass the ORM still get values. `is_active`, `is_superuser` and
  `token_version` have server defaults too — a raw `INSERT` needs only
  `id`/`email`/`password`.
- `updated_at` is bumped **by the application** (`onupdate=utcnow`), not by the
  database. Postgres has no `ON UPDATE` column clause — the equivalent takes a
  plpgsql function plus a `BEFORE UPDATE` trigger — and a trigger would not
  exist in the SQLite test suite, so ORM updates and raw SQL would disagree.
  If you ever need raw-SQL updates to bump it, add the trigger **and** mirror
  it in tests.
- A column that is `NOT NULL` needs a matching `server_default`, and the
  migration must declare it too: `env.py` sets `compare_server_default=True`, so
  `alembic check` fails on any mismatch.
- Foreign keys point at the plural table name (e.g. `users.id`).

### Rules

- Use the injected `*Dep` aliases from `app/api/deps.py` (`CurrentUser`,
  `CurrentSuperuser`, `UserServiceDep`, `AuthServiceDep`, …). Routes must not
  import `Session`, SQL, or repositories.
- Settings live in `app/core/config.py` (`pydantic-settings`). Read them via
  `settings.<NAME>`. Add new variables to `.env.backend.example` at the same
  time.
- List-typed env vars must be declared as
  `Annotated[list[str], NoDecode]` plus a validating `field_validator`.
  Without `NoDecode`, pydantic-settings JSON-decodes the value before the
  validator runs and comma-separated input raises `SettingsError`.
- Never `print()` (ruff `T201`). Never raise `HTTPException` without `from exc`
  for wrapped errors.
- **Context managers annotate generators, not iterators.** `@contextmanager`
  functions return `Generator[T]`; `@asynccontextmanager` functions return
  `AsyncGenerator[T]`. Annotating `Iterator[T]` / `AsyncIterator[T]` is
  deprecated by typeshed (`reportDeprecated`) and is the kind of thing that
  breaks on a stdlib bump.
- Deprecations are a build failure, not a warning: `pytest` runs with
  `DeprecationWarning` and `PendingDeprecationWarning` promoted to errors
  (`filterwarnings` in `backend/pyproject.toml`). If a dependency starts
  warning, pin it or fix the call — do not blanket-ignore the category.
- Formatting is `ruff format`, linting is `ruff check`, line length 100.

### Response format

Success bodies are wrapped so a client always knows where the payload is:

```json
{ "data": { "message": "ok" } }
```

Collections add `meta` (the JSON:API arrangement — `data` / `meta`, with room
for `links` later):

```json
{
  "data": [{ "id": "…", "email": "a@example.com" }],
  "meta": {
    "total_count": 57, "page": 2, "per_page": 25,
    "total_pages": 3, "has_next": true, "has_previous": true
  }
}
```

- Use `Envelope[T]` / `PaginatedEnvelope[T]` from `app/models/common.py`
  (`response_model=Envelope[UserPublic]`), and build collections with the
  `paginated(items, total_count=…, page=…, per_page=…)` helper so the derived
  counts stay in one place. A route must never return a bare list.
- Errors are the one exception: they use `{"error": {...}}` (see below) because
  a failure has no `data`.
- `204 No Content` responses keep an empty body — there is nothing to wrap.

### Error format

`api/errors.py` is the only place that builds an error body. Every failure —
domain, validation, routing (`404`/`405`) or an unhandled exception — returns
the same envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Password: Must be at least 8 characters long.",
    "details": [{ "field": "password", "message": "Must be at least 8 characters long." }]
  }
}
```

- `code` is stable and machine-readable. For domain errors it is derived from
  the class name (`EmailAlreadyExistsError` → `email_already_exists`), so a new
  subclass needs no extra wiring; everything else uses the status mapping in
  `_HTTP_CODES`.
- `message` is a sentence for a human. Single-field validation errors read
  `Field: reason`; several errors summarise and leave the specifics in
  `details`.
- `details` exists only for field-level validation problems.
- `api/errors.py` also translates Pydantic's `type` codes into sentences. Add a
  branch to `_describe` when a new validator produces an ugly one; never let
  `loc`/`input`/`ctx` reach the client.
- `ErrorResponse` in `app/models/common.py` documents this shape in OpenAPI —
  use it in a route's `responses={...}` instead of describing errors by hand.

### Collection endpoints

Grids share one query-string contract: `app/api/params.py` (`PageParamsDep`)
parses it and `app/services/pagination.py` (`resolve_order_by`) validates the
sort allowlist.

```
GET /api/v1/users/?page=2&per_page=25&q=acme&sort=-created_at,email
```

- `page` is 1-based, `per_page` defaults to 25 and is capped at 100.
- `q` searches the resource's `SEARCHABLE` columns (`ILIKE`); a `%` in the term
  is escaped, so it matches literally.
- `sort` only accepts names in the repository's `SORTABLE` map — a query-string
  value must never reach `ORDER BY` unchecked. Add the field to that map
  instead of relaxing the check. The parameter is capped (`max_length=200`) and
  at most 5 fields are honoured; both limits are `400`/`422`, never a 500.
- Always append a unique column (`User.id`) to `order_by`, otherwise rows can
  repeat or vanish between pages when a sort column has ties.
- New filters become sibling query parameters and conditions passed to
  `SqlRepository.fetch_page`; paging/search/sort already compose with them.

### Adding a table

```bash
make backend-revision m="add things"
# then EDIT the generated file:
#   * autogenerate omits `import sqlmodel` but uses sqlmodel.sql.sqltypes.*
#   * autogenerate may reorder columns — put `id` first yourself
make backend-migrate
```

`alembic/versions/` starts from one squashed baseline revision
(`04c9660d5f43` — both tables). Do not add to that file: new schema changes get a
new revision, so deployed databases can be upgraded. Squash again only before a
first release, and tell whoever runs it to recreate or `alembic stamp` their
database, because the old revision ids stop existing.

`AUTO_CREATE_SCHEMA=true` (local default) runs `alembic upgrade head` on boot
and seeds `FIRST_SUPERUSER`. It uses Alembic rather than
`SQLModel.metadata.create_all` deliberately: `create_all` writes no
`alembic_version` row, so a database created that way can never be migrated
(the first real migration fails with "relation already exists"). Deployed
environments use `AUTO_CREATE_SCHEMA=false` and run `alembic upgrade head` as a
release step before the new tasks take traffic — the image has no
migrate-then-start entrypoint.

## Frontend conventions

- All HTTP goes through `src/api/client.ts`. Add typed functions there instead
  of calling `fetch` in components. It handles the bearer token and throws
  `ApiError`, which carries `status`, `code`, `message` and (for invalid
  payloads) per-field `details`.
- **Two shells, chosen by route meta.** `App.vue` renders `PublicLayout`
  (centred card, no chrome) when `meta.layout === "public"` and
  `PrivateLayout` (app bar + drawer) otherwise, so an unmarked route is private
  by default. Public pages are the sign-in/reset/onboarding flows; future
  ones (`/forgot-password`, `/reset-password`, `/accept-invitation`) need only
  a route record with `meta: { layout: "public" }`.
- Route meta is typed in `src/router/meta.d.ts` (`title`, `layout`,
  `requiresAuth`, `guestOnly`). `requiresAuth` redirects to `login` with a
  `redirect` query; `guestOnly` bounces a signed-in user to the dashboard.
- Auth state lives in `src/composables/useAuth.ts` (module-level refs shared by
  every caller). Do not re-implement login state per component.
- Route protection is expressed in the route table (`meta.requiresAuth`),
  enforced by `router.beforeEach`. Do not duplicate guards in components or
  layouts.
- Components use `<script setup lang="ts">` and Vuetify components
  (`v-card`, `v-btn`, …). Icons are MDI (`mdi-*`). Styling is via Vuetify
  utility classes, not a separate CSS framework.
- Path alias `@/` maps to `src/`.
- `build` runs `vue-tsc --noEmit && vite build` — a type error fails the build.

### Dev-only UI must stay out of production bundles

Mailpit and API-docs affordances are for local development. They are loaded via
`defineAsyncComponent` behind `import.meta.env.DEV`:

```ts
const DevToolsLinks = import.meta.env.DEV
  ? defineAsyncComponent(() => import("@/components/DevToolsLinks.vue"))
  : null;
```

Do **not** replace this with a `v-if="isDev"` around inline markup — the
strings then still ship in the bundle. After changing anything in this area:

```bash
docker run --rm fastapi-vuetify-frontend-build sh -c "grep -rio 'mailpit' /app/frontend/dist | wc -l"
# must print 0
```

## Agent skills

`.agents/skills/` holds skills vendored from the libraries we depend on:
`fastapi/` and `sqlmodel/`. They are checked in as **regular files**, not
symlinks or a submodule.

- **Why vendored, not symlinked.** Upstream ships skills inside the installed
  package (`<site-packages>/<dist>/.agents/skills/<name>/`). Symlinking to that
  path resolves today and breaks for anyone who clones without running
  `make install` first — and `docker cp`/CI checkouts turn dangling links into
  empty files silently. Copies of ~50 kB total cost nothing and always resolve.
- **They are a snapshot, not a source of truth.** They document upstream
  conventions (`Annotated[..., Depends(...)]`, SQLModel over raw SQLAlchemy,
  `UTCDateTime`). Where they disagree with this file, **this file wins**: this
  repo declares table columns explicitly instead of inheriting from `XBase`, and
  sorts by an allowlist. Re-apply local judgement rather than following a skill
  literally.
- **Refreshing a skill** after bumping a dependency: copy the directory out of
  a built image, then re-apply any local edits.
  ```bash
  cid=$(docker create fastapi-vuetify-backend-dev)
  docker cp "$cid":/app/.venv/lib/python3.15/site-packages/fastapi/.agents/skills/fastapi .agents/skills/
  docker rm "$cid"
  ```
  Do not switch this to `library-skills` symlinks — that writes relative links
  into `.venv/`, which the repo does not commit.
- Don't add a skill for a package we don't depend on (`typer` ships one; it is
  only transitive CLI tooling here and was deliberately skipped).

## Authentication

- Tokens are HS256 JWTs created and verified **only** in
  `app/core/security.py` by `AccessTokenCodec` (`encode`/`decode`);
  `deps.get_current_user` is the only place that resolves a token to a `User`.
- `AccessTokenCodec.decode` pins `algorithms=[ALGORITHM]` and requires the
  claims `exp`, `iat`, `sub`, `iss`, `aud`, `jti`, `ver`. **Do not** add a
  fallback decode path, pass `options={"verify_signature": False}`, or accept a
  token algorithm from the token itself — that is exactly how JWTs get forged.
- `SECRET_KEY` must be ≥32 characters (RFC 7518 §3.2). `Settings` refuses to
  construct otherwise unless `ENVIRONMENT=local`, so a deployed API will not
  boot with a short key.
- `ver` must equal `users.token_version`. Password changes bump it to revoke
  outstanding tokens; keep that invariant when adding auth flows.
- **Refresh tokens are opaque, not JWTs.** They live in `refresh_tokens` and
  only their SHA-256 digest is stored (`RefreshTokenGenerator.digest`). Each
  refresh **rotates**: the presented row is marked `revoked_at` and a new row
  joins the same `family_id`. Seeing a revoked token again means replay, so
  `RefreshTokenRepository.revoke_family` kills the chain. Never store or log the
  plaintext. Consumption is a single conditional `UPDATE`
  (`RefreshTokenRepository.consume`), so two concurrent refreshes of the same
  token cannot both succeed — the loser is treated as a replay. Keep that
  atomicity: a read-then-write check is racy.
- Any new credential-changing flow must call
  `RefreshTokenRepository.revoke_all_for_user` **and** bump `token_version`, or one of the
  two token types stays valid.
- Errors from verification are swallowed into a single `401` so failures are
  not distinguishable to an attacker.
- Failed sign-ins are throttled in-process (`app/core/throttle.py`): 10 per
  account and 30 per caller per minute, answered with `429` + `Retry-After`.
  Only failures count and a success resets the account's counter. This is a
  per-task mitigation, not a replacement for edge rate limiting at the ALB/WAF.
- `refresh_tokens.user_id` is `ON DELETE CASCADE`: deleting a user must remove
  their sessions. Without it, `DELETE /users/{id}` fails with a FK violation
  and the API answers `500` for every user who has ever signed in.
- Never log a token or a password. The frontend keeps the token in
  `localStorage` and clears it on `401`; see the README for the tradeoff.

## Environment and configuration

- **One env file per app, in the repo root.** Compose loads them with
  `env_file:`; there are no inline `environment:` blocks, so what the container
  sees is exactly the file, and the `*.example` next to it documents it.

  | File            | Loaded by | `make init` creates it from |
  | --------------- | --------- | --------------------------- |
  | `.env.backend`  | `db` + `backend` | `.env.backend.example` |
  | `.env.frontend` | Vite dev server | `.env.frontend.example` |

  The generated files are git-ignored (`.gitignore` keeps only `*.example`).
  Add new keys to the `.example` file and to `app/core/config.py` together.
- `db` loads `.env.backend` too: it only reads `POSTGRES_*` (Postgres ignores
  the rest) and sharing the file keeps those credentials and `DATABASE_URL` in
  lockstep, so renaming a database cannot break the connection string.
- Email has one provider switch, `EMAIL_PROVIDER`:
  - `smtp` (default, and what `.env.backend.example` ships) — generic SMTP
    relay. Locally it points at Mailpit (`mailpit:1025` inside Compose,
    `localhost:1025` when the API runs on the host).
  - `ses` — Amazon SES over its SMTP interface. The host is derived from
    `SES_REGION` (`email-smtp.<region>.amazonaws.com:587`, STARTTLS) and the
    credentials are SES SMTP credentials, **not** the AWS secret access key.
  - Missing configuration does not stop the API booting; `EmailSender`
    reports `is_configured == False` and raises a clear error on send.
- **Mailpit is local-development only.** It is defined exclusively in
  `compose.override.yml`. Never add it to `compose.yml` and never give the
  deployed backend a `mailpit` hostname.

Quick check after touching Compose or env files:

```bash
make init                                        # creates any missing file
docker compose config --services                 # db, mailpit, backend, frontend
docker compose -f compose.yml config --services  # db, backend
```

## Containers and CI

- Use official images only. Docker Official Images for `python`, `node`,
  `postgres`, `docker`; `ghcr.io/astral-sh/uv` is Astral's official
  image; `axllent/mailpit` is Mailpit's official image (no Docker Official
  Image exists for it).
- Pin versions as build args at the top of each Dockerfile
  (`PYTHON_VERSION`, `UV_VERSION`, `NODE_VERSION`, `PNPM_VERSION`). Do not
  introduce floating tags (`:latest`, `:alpine`) for base images.
- Docker cannot expand variables inside `COPY --from=`, so the uv binary is
  copied from a named stage:
  ```dockerfile
  FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
  ...
  COPY --from=uv /uv /uvx /bin/
  ```
- The backend Dockerfile is multi-stage: `dev` (hot reload) and `runtime`
  (slim, non-root). The backend runtime image has **no
  `HEALTHCHECK`** — liveness is owned by the AWS ALB target group, which probes
  `/api/v1/health/`. Do not reintroduce an in-image probe.
- **The frontend has no runtime image.** It is a static site: the `build`
  target emits `frontend/dist`, which is uploaded to the S3 bucket website.
  `compose.override.yml` builds the `dev` target for the Vite server, and that
  is the only place a frontend container exists. Do not add an nginx stage or
  a proxy config back — there is nothing in production for it to proxy.
- The API runs `uvicorn` directly (no gunicorn). Behind the ALB, set
  `FORWARDED_ALLOW_IPS` to the ALB/VPC CIDRs so `X-Forwarded-For`/`-Proto` are
  trusted; otherwise uvicorn ignores them and every client looks like the ALB.
- Lockfiles are committed. Docker and CI install with `--frozen-lockfile` /
  `uv sync`, so regenerate them after dependency changes:
  `make backend-lock` and `make frontend-install`.
- **GitHub Actions is the default CI** (`.github/workflows/backend.yml` and
  `frontend.yml`). It runs on pushes to `main` and on pull requests, path
  filtered, and executes the same checks as `make check` plus the
  `frontend/dist` dev-string grep. Keep the two workflows in step with
  `Makefile` targets when either changes.
- A GitLab pipeline is kept as an optional alternative: `.gitlab-ci.yml`
  includes `ci/backend.gitlab-ci.yml` and `ci/frontend.gitlab-ci.yml`. Pipelines
  can build either side: `BUILD_ALL=true`, `BUILD_BACKEND=true`,
  `BUILD_FRONTEND=true`, or `BUILD_*=false` to skip. With no variables, changes
  are detected from the diff; unmatched jobs become manual.

## Invariants — do not break these

| Invariant | Why |
| --------- | --- |
| TypeScript stays on 5.9.x | `vue-tsc` 3.3.x crashes on TypeScript 7 (`./lib/tsc` no longer exported). |
| Tables are plural, `id` is a UUID first column | House style; `id`-first breaks if a table inherits a column-bearing base. |
| `postgres:18` volume mounted at `/var/lib/postgresql` | Not `.../data`; `18-alpine` creates a versioned subdirectory. |
| Mailpit only in `compose.override.yml` | It is a dev tool; deployed email must use a real relay. |
| No `mailpit`/`8025` strings in `frontend/dist` | Verified by grep; keep dev tooling behind `import.meta.env.DEV`. |
| Alembic files import `sqlmodel` | Autogenerate references `sqlmodel.sql.sqltypes.*` without the import. |
| `SECRET_KEY` is not `changethis` in any deployed env | JWT signing key. |
| Lockfiles committed and frozen in Docker/CI | Reproducible builds. |
| `.agents/skills/` are real files, never symlinks into `.venv` | The venv is not committed; links break on a fresh clone and go empty in `docker cp`. |

## Gotchas

- `pydantic-settings` + list env var → `NoDecode` (see above).
- pnpm 12 rewrites `pnpm-workspace.yaml` when it needs a supply-chain
  exemption; `minimumReleaseAge: 0` is set deliberately to keep installs
  deterministic. Do not remove it without checking CI.
- Ports 5432/8000 are commonly occupied on developer machines; override
  `POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT` (they default to the values
  in `compose.yml`; export them in the shell to override).
- The Vite dev server caches pre-bundled deps; after adding dynamic imports,
  reload the page (or restart the container) if you see
  `504 (Outdated Optimize Dep)`.
