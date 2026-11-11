SHELL := /bin/bash

COMPOSE ?= docker compose
PROD_COMPOSE := $(COMPOSE) -f compose.yml
BACKEND := cd backend && uv run
FRONTEND := pnpm --filter @app/frontend

.DEFAULT_GOAL := help

.PHONY: help init install check \
        backend-install backend-lock backend-fmt backend-lint backend-test \
        backend-dev backend-migrate backend-revision \
        frontend-install frontend-dev frontend-build frontend-typecheck \
        dev up down down-v logs ps docker-build

# Fail early with an actionable message instead of "command not found".
_require = command -v $(1) >/dev/null || { echo "$(1) is not installed - see AGENTS.md for the Docker equivalent"; exit 1; }
_require-env = for f in $(1); do [ -f $$f ] || { echo "missing $$f - run 'make init'"; exit 1; }; done

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
init: ## Create .env.backend / .env.frontend with a random SECRET_KEY
	@for f in .env.backend .env.frontend; do \
		[ -f "$$f" ] || { cp "$$f.example" "$$f"; echo "Created $$f"; }; \
	done
	@if grep -q '^SECRET_KEY=changethis$$' .env.backend; then \
		sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$$(openssl rand -hex 32)|" .env.backend && rm -f .env.backend.bak; \
		echo "Generated a random SECRET_KEY"; \
	fi

install: backend-install frontend-install ## Install dependencies

check: backend-lint backend-test frontend-typecheck ## Lint + test everything (the gate)

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
backend-install: ## Sync the backend virtualenv
	@$(call _require,uv)
	cd backend && uv sync

backend-lock: ## Regenerate backend/uv.lock
	@$(call _require,uv)
	cd backend && uv lock

backend-fmt: ## Format + autofix the backend
	@$(call _require,uv)
	cd backend && uv run ruff format . && uv run ruff check --fix .

backend-lint: ## Check lint and formatting
	@$(call _require,uv)
	cd backend && uv run ruff check . && uv run ruff format --check .

backend-test: ## Run the test suite
	@$(call _require,uv)
	$(BACKEND) pytest

backend-dev: ## Run the API with autoreload on :8000
	@$(call _require,uv)
	$(BACKEND) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

backend-migrate: ## Apply migrations
	@$(call _require,uv)
	$(BACKEND) alembic upgrade head

backend-revision: ## Create a migration: make backend-revision m="add x"
	@$(call _require,uv)
	$(BACKEND) alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
frontend-install: ## Install workspace dependencies
	@$(call _require,pnpm)
	pnpm install

frontend-dev: ## Run the Vite dev server on :5173
	@$(call _require,pnpm)
	$(FRONTEND) dev

frontend-build: ## Build the static bundle into frontend/dist
	@$(call _require,pnpm)
	$(FRONTEND) build

frontend-typecheck: ## Type-check Vue + TS
	@$(call _require,pnpm)
	$(FRONTEND) typecheck

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
dev: ## Start the dev stack in the foreground
	@$(call _require-env,.env.backend .env.frontend)
	$(COMPOSE) up --build

up: ## Start the deployed-like stack in the background
	@$(call _require-env,.env.backend)
	$(PROD_COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

down-v: ## Stop the stack and delete volumes (database!)
	$(COMPOSE) down -v

logs: ## Follow logs
	$(COMPOSE) logs -f --tail=100

ps: ## Show running services
	$(COMPOSE) ps

docker-build: ## Build the deployed-like images
	$(PROD_COMPOSE) build
