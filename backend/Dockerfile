# syntax=docker/dockerfile:1

# Multi-stage build. `dev` is used by compose.override.yml (hot reload),
# `runtime` is the small production image.
#
# Base images (all official):
#   - docker.io/library/python  (Docker Official Image)
#   - ghcr.io/astral-sh/uv      (official image published by Astral)
ARG PYTHON_VERSION=3.15
ARG UV_VERSION=0.13.7

# ---------------------------------------------------------------------------
# uv binary (official image published by Astral), pinned by version
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------------------------------------------------------------------------
# Base: CPython + uv
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS base

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ---------------------------------------------------------------------------
# Dependencies (cached layer, changes only when the manifest changes)
# ---------------------------------------------------------------------------
FROM base AS deps

COPY backend/pyproject.toml backend/uv.lock* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# ---------------------------------------------------------------------------
# Development image
# ---------------------------------------------------------------------------
FROM base AS dev

COPY backend/pyproject.toml backend/uv.lock* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

COPY backend/ ./

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Runtime image
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=deps --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app backend/app ./app
COPY --chown=app:app backend/alembic ./alembic
COPY --chown=app:app backend/alembic.ini ./alembic.ini

USER app

EXPOSE 8000

# Deliberately no HEALTHCHECK: liveness/readiness is owned by the AWS ALB target
# group, which probes /api/v1/health/ itself. An in-image probe would
# only duplicate that and couple container health to HTTP.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
