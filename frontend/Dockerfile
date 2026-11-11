# syntax=docker/dockerfile:1

# Two targets: `dev` (Vite dev server, used by compose.override.yml) and `build`
# (the static bundle uploaded to S3). There is deliberately no runtime image —
# the frontend is served by S3, not by a container.
ARG NODE_VERSION=26
ARG PNPM_VERSION=12.18.0

# ---------------------------------------------------------------------------
# Base: Node + pnpm
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS base

ARG PNPM_VERSION
RUN npm install -g pnpm@${PNPM_VERSION}

WORKDIR /app
ENV CI=true

# ---------------------------------------------------------------------------
# Workspace dependencies (cached layer)
# ---------------------------------------------------------------------------
FROM base AS deps

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY frontend/package.json ./frontend/package.json

RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# ---------------------------------------------------------------------------
# Development image (Vite dev server)
# ---------------------------------------------------------------------------
FROM deps AS dev

COPY frontend ./frontend

EXPOSE 5173
CMD ["pnpm", "--filter", "@app/frontend", "dev", "--host", "0.0.0.0", "--port", "5173"]

# ---------------------------------------------------------------------------
# Build the static bundle (artifact: /app/frontend/dist)
# ---------------------------------------------------------------------------
FROM deps AS build

ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}

COPY frontend ./frontend

RUN pnpm --filter @app/frontend build
