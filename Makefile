SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

ENV_FILE ?= .env
PROJECT_NAME ?= hera
PYTHON ?= .venv/bin/python
SERVICE ?= backend
TAIL ?= 100
BACKUP_DIR ?= $(CURDIR)/backups
RESTORE_FILE ?=
CONFIRM_RESTORE ?= NO
CONFIRM_ROLLBACK ?= NO
CONFIRM_SCHEMA_COMPATIBLE ?= NO
CONFIRM_EXTREME ?= NO
CONFIRM_DATA_EXPORT ?= NO
CONFIRM_DATA_REBIND ?= NO
CONFIRM_DATA_RESET ?= NO
CONFIRM_MODEL_PREFLIGHT ?= NO
DEV_PROJECT_NAME ?= hera-dev
REPLICAS ?= 2

ENV_ARGS = $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)
COMPOSE = docker compose $(ENV_ARGS) -p $(PROJECT_NAME) -f docker-compose.yml
MONITORING_COMPOSE = $(COMPOSE) -f docker-compose.monitoring.yml

.PHONY: help setup config-check lint unit integration test test-full data-generate generated-validate data-validate db-bootstrap migrate seed data-import data-export data-rebind-export data-reset-dev up down restart status logs scale smoke model-preflight stress stress-ci stress-extreme monitoring-up monitoring-down monitoring-status monitoring-logs package deploy release-check backup restore rollback

help: ## Show every supported target and its purpose.
	@awk 'BEGIN {FS = ":.*##"; printf "HERA commands:\n\n"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install local developer dependencies and create an ignored .env template.
	@command -v docker >/dev/null || { echo "Docker is required."; exit 1; }
	@docker compose version >/dev/null
	@command -v python3 >/dev/null || { echo "python3 is required."; exit 1; }
	@command -v npm >/dev/null || { echo "npm is required for frontend development."; exit 1; }
	@if [[ ! -f "$(ENV_FILE)" ]]; then cp .env.example "$(ENV_FILE)"; chmod 600 "$(ENV_FILE)"; echo "Created $(ENV_FILE); add API_KEY before deploy."; fi
	@python3 -m venv .venv
	@$(PYTHON) -m pip install --upgrade pip
	@$(PYTHON) -m pip install -r apps/backend/requirements.txt -r requirements-dev.txt
	@npm --prefix apps/frontend ci

config-check: ## Validate secrets/config quietly and verify the PostgreSQL seed archive.
	@$(COMPOSE) config --quiet
	@$(MONITORING_COMPOSE) config --quiet
	@$(PYTHON) apps/backend/scripts/verify_release_assets.py --seed-archive apps/backend/data/hera_postgres_seed.json.gz --generated-dir data/generated --require-generated --expected-bundle-version 2.0.0 >/dev/null
	@echo "Configuration and seed archive are valid."

data-generate: ## Rebuild generated JSON from raw sources; does not modify PostgreSQL/seed.
	@node scripts/build-generated-data.mjs
	@$(MAKE) generated-validate
	@echo "Generated data is valid. PostgreSQL and the release seed were not changed."

generated-validate: ## Validate raw hashes + generated exact-set without comparing the PG seed.
	@$(PYTHON) apps/backend/scripts/verify_generated_data.py --generated-dir data/generated --expected-bundle-version 2.0.0

data-validate: ## Validate raw inputs, exact generated set, manifest, seed and checksums.
	@$(PYTHON) apps/backend/scripts/verify_release_assets.py --seed-archive apps/backend/data/hera_postgres_seed.json.gz --generated-dir data/generated --require-generated --expected-bundle-version 2.0.0

lint: ## Run backend Ruff plus frontend TypeScript checks.
	@$(PYTHON) -m ruff check apps/backend/app apps/backend/tests apps/backend/scripts scripts
	@npm --prefix apps/frontend run typecheck

unit: ## Run fast backend tests outside integration/ plus frontend unit tests.
	@$(PYTHON) -m pytest apps/backend/tests --ignore=apps/backend/tests/integration
	@npm --prefix apps/frontend test

integration: ## Run backend integration tests against configured dependencies.
	@$(PYTHON) -m pytest apps/backend/tests/integration

test: test-full ## Alias for the complete offline test suite.

test-full: lint ## Run all backend/frontend tests and the production frontend build.
	@$(PYTHON) -m pytest
	@npm --prefix apps/frontend test
	@npm --prefix apps/frontend run build

migrate: ## Apply every pending Alembic migration to PostgreSQL.
	@$(COMPOSE) run --rm migrate

seed: ## Verify and idempotently upsert the pinned archive into PostgreSQL.
	@$(COMPOSE) run --rm seed

db-bootstrap: data-validate ## After clone/pull: build API, start PostgreSQL, migrate and seed.
	@$(COMPOSE) build backend
	@$(COMPOSE) up -d --wait --wait-timeout 120 db
	@$(COMPOSE) run --rm migrate
	@$(COMPOSE) run --rm seed
	@echo "PostgreSQL is migrated and seeded; its named volume was preserved."

data-import: data-validate ## Migrate then import committed seed into an empty/same-release DB.
	@$(COMPOSE) build backend
	@$(COMPOSE) run --rm migrate
	@$(COMPOSE) run --rm seed

data-export: ## Overwrite seed from canonical PostgreSQL only with CONFIRM_DATA_EXPORT=YES.
	@if [[ "$(CONFIRM_DATA_EXPORT)" != "YES" ]]; then echo "Refusing: rerun with CONFIRM_DATA_EXPORT=YES after reviewing PostgreSQL."; exit 2; fi
	@$(COMPOSE) build backend
	@$(COMPOSE) run --rm migrate
	@$(COMPOSE) --profile tools run --rm --no-deps data-export
	@$(PYTHON) apps/backend/scripts/verify_release_assets.py --seed-archive apps/backend/data/hera_postgres_seed.json.gz --generated-dir data/generated --require-generated --expected-bundle-version 2.0.0

data-rebind-export: ## Expert-only: bind reviewed PG rows to a new generated manifest.
	@if [[ "$(CONFIRM_DATA_EXPORT)" != "YES" || "$(CONFIRM_DATA_REBIND)" != "YES" ]]; then echo "Refusing: require CONFIRM_DATA_EXPORT=YES CONFIRM_DATA_REBIND=YES."; exit 2; fi
	@$(COMPOSE) build backend
	@$(COMPOSE) run --rm migrate
	@$(COMPOSE) --profile tools run --rm --no-deps data-export python /app/scripts/export_postgres_seed.py --template /app/data/hera_postgres_seed.json.gz --output /export/hera_postgres_seed.json.gz --generated-dir /source-generated --confirm-overwrite --rebind-generated-manifest --confirm-rebind REVIEWED_CANONICAL_POSTGRES
	@$(MAKE) data-validate

data-reset-dev: data-validate ## Reset only dedicated dev/demo/test DB; CONFIRM_DATA_RESET=YES.
	@CONFIRM_DATA_RESET="$(CONFIRM_DATA_RESET)" DEV_PROJECT_NAME="$(DEV_PROJECT_NAME)" ENV_FILE="$(ENV_FILE)" bash scripts/reset-dev-data.sh

up: ## Build and start the base stack, then wait for readiness.
	@$(COMPOSE) up -d --build --wait --wait-timeout 240

down: ## Stop/remove containers and networks but preserve every named volume.
	@$(COMPOSE) down

restart: ## Restart backend/frontend without rebuilding or deleting state.
	@$(COMPOSE) restart backend frontend

status: ## Show running, one-shot and unhealthy services.
	@$(COMPOSE) ps --all

logs: ## Follow bounded logs; override SERVICE=frontend and/or TAIL=200.
	@$(COMPOSE) logs --follow --tail "$(TAIL)" "$(SERVICE)"

scale: ## Scale stateless API replicas behind Nginx; e.g. make scale REPLICAS=3.
	@if ! [[ "$(REPLICAS)" =~ ^[1-9][0-9]*$$ ]]; then echo "REPLICAS must be a positive integer."; exit 2; fi
	@$(COMPOSE) up -d --no-deps --scale "backend=$(REPLICAS)" backend frontend
	@$(COMPOSE) ps backend frontend

smoke: ## Run same-origin readiness/structured/booking/emergency smoke checks.
	@$(COMPOSE) exec -T backend python scripts/smoke_deploy.py --base-url http://frontend

model-preflight: ## Spend exactly one LLM+embedding probe only with explicit confirmation.
	@if [[ "$(CONFIRM_MODEL_PREFLIGHT)" != "YES" ]]; then echo "Refusing paid probe: rerun with CONFIRM_MODEL_PREFLIGHT=YES."; exit 2; fi
	@$(COMPOSE) run --rm --no-deps backend python scripts/verify_model_gateway.py

stress: ## Run standard mixed stress in an isolated loopback-only project; zero model calls.
	@bash scripts/run-stress.sh --profile standard --scenario mixed --replicas 1 --min-replicas 1

stress-ci: ## Run the small CI mixed stress profile; set STRESS_BUILD=0 after images are built.
	@bash scripts/run-stress.sh --profile ci --scenario mixed --replicas 1 --min-replicas 1

stress-extreme: ## Run extreme mixed stress across exactly 3 replicas after explicit confirmation.
	@if [[ "$(CONFIRM_EXTREME)" != "YES" ]]; then echo "Refusing: rerun with CONFIRM_EXTREME=YES."; exit 2; fi
	@bash scripts/run-stress.sh --profile extreme --scenario mixed --replicas 3 --min-replicas 3 --confirm-extreme

monitoring-up: ## Start app, Prometheus and Grafana; ports remain loopback-only.
	@$(MONITORING_COMPOSE) up -d --wait --wait-timeout 240

monitoring-down: ## Stop monitoring containers while preserving metrics/dashboard volumes.
	@$(MONITORING_COMPOSE) stop prometheus grafana

monitoring-status: ## Show application, Prometheus and Grafana health/state.
	@$(MONITORING_COMPOSE) ps --all

monitoring-logs: ## Follow bounded Prometheus/Grafana logs; override TAIL=200.
	@$(MONITORING_COMPOSE) logs --follow --tail "$(TAIL)" prometheus grafana

package: ## Build a secret-free ZIP, release metadata and two checksum layers on Ubuntu.
	@bash scripts/package-release.sh

deploy: ## One-command build, verify, migrate, seed, readiness, smoke and monitoring; no paid probe.
	@bash scripts/deploy.sh --monitoring

release-check: ## Verify the image's seed archive without model/API calls.
	@$(COMPOSE) run --rm --no-deps backend python scripts/verify_release_assets.py --seed-archive /app/data/hera_postgres_seed.json.gz --expected-bundle-version 2.0.0

backup: ## Create a permission-restricted PostgreSQL logical backup; no secret is printed.
	@BACKUP_DIR="$(BACKUP_DIR)" bash scripts/backup.sh

restore: ## Destructive restore only with RESTORE_FILE=... CONFIRM_RESTORE=YES.
	@RESTORE_FILE="$(RESTORE_FILE)" CONFIRM_RESTORE="$(CONFIRM_RESTORE)" bash scripts/restore.sh

rollback: ## Image rollback only after backup and explicit schema-compatibility confirmations.
	@CONFIRM_ROLLBACK="$(CONFIRM_ROLLBACK)" CONFIRM_SCHEMA_COMPATIBLE="$(CONFIRM_SCHEMA_COMPATIBLE)" bash scripts/rollback.sh
