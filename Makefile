# Error: "*** missing separator." -> replace spaces with tabs

help:
	@echo "Error: Please specify a target."
	@echo "Usage: make [deploy|test|debug|prod-build|prod-migrate|prod-downgrade|prod-run|prod-logs|prod-stop|dev-build|dev-migrate|dev-downgrade|dev-run|dev-logs|dev-stop|gitlab-runner|gitlab-runner-stop]"
	@exit 1

.PHONY: dev-build dev-build-logs dev-migrate dev-downgrade dev-run dev-attach dev-logs dev-logs-all dev-stop debug prod-build prod-build-logs prod-migrate prod-downgrade prod-run prod-logs prod-logs-all prod-stop deploy test gitlab-runner gitlab-runner-stop

VERSION := $(shell git describe --tags --abbrev=0)
CLEAN_VERSION := $(shell echo $(VERSION) | sed 's/^v//')
OVERRIDE_FILE := $(wildcard compose.override.yaml)

OVERRIDE_FILE ?= compose.override.yaml
ifneq ($(wildcard $(OVERRIDE_FILE)),)
    OVERRIDE_FLAG := -f $(OVERRIDE_FILE)
else
    OVERRIDE_FLAG :=
endif

ENV_FILE ?= .env
ifneq ($(wildcard $(ENV_FILE)),)
	ENV_FILE_FLAG := --env-file $(ENV_FILE)
else
	ENV_FILE_FLAG :=
endif


COMPOSE_DEV := docker compose -f compose.dev.yaml $(OVERRIDE_FLAG) -p opengsync-dev $(ENV_FILE_FLAG)
COMPOSE_PROD := docker compose -f compose.yaml $(OVERRIDE_FLAG) -p opengsync-prod $(ENV_FILE_FLAG)
COMPOSE_TEST := docker compose -f compose.test.yaml -p opengsync-test
LOGS = opengsync-app

dev-build:
	$(COMPOSE_DEV) build --build-arg VERSION=$(VERSION)

dev-build-logs:
	$(COMPOSE_DEV) build --progress=plain --build-arg VERSION=$(VERSION)

dev-migrate:
	$(COMPOSE_DEV) run --rm db-migrator sh -c 'set -eu; echo "Current migration before upgrade:"; alembic --config /app/alembic.ini current 2>/dev/null; alembic --config /app/alembic.ini upgrade head; echo "Current migration after upgrade:"; alembic --config /app/alembic.ini current 2>/dev/null'

dev-downgrade:
	$(COMPOSE_DEV) run --rm db-migrator sh -c 'set -eu; before="$$(alembic --config /app/alembic.ini current 2>/dev/null)"; alembic --config /app/alembic.ini downgrade -1; after="$$(alembic --config /app/alembic.ini current 2>/dev/null)"; printf "Migration removed (previous current):\\n%s\\nCurrent migration:\\n%s\\n" "$$before" "$$after"'

dev-run:
	$(COMPOSE_DEV) up -d --remove-orphans

dev-attach:
	$(COMPOSE_DEV) up --remove-orphans

dev-logs:
	$(COMPOSE_DEV) logs -f $(LOGS)

dev-logs-all:
	$(COMPOSE_DEV) logs -f

dev-stop:
	$(COMPOSE_DEV) stop

debug: dev-build dev-run dev-logs

prod-build:
	$(COMPOSE_PROD) build --build-arg VERSION=$(VERSION)

prod-build-logs:
	$(COMPOSE_PROD) build --progress=plain --build-arg VERSION=$(VERSION)

prod-migrate:
	$(MAKE) test
	$(COMPOSE_PROD) run --rm db-migrator sh -c 'set -eu; echo "Current migration before upgrade:"; alembic --config /app/alembic.ini current 2>/dev/null; alembic --config /app/alembic.ini upgrade head; echo "Current migration after upgrade:"; alembic --config /app/alembic.ini current 2>/dev/null'

prod-downgrade:
	$(COMPOSE_PROD) run --rm db-migrator sh -c 'set -eu; before="$$(alembic --config /app/alembic.ini current 2>/dev/null)"; alembic --config /app/alembic.ini downgrade -1; after="$$(alembic --config /app/alembic.ini current 2>/dev/null)"; printf "Migration removed (previous current):\\n%s\\nCurrent migration:\\n%s\\n" "$$before" "$$after"'

prod-run:
	$(COMPOSE_PROD) up -d --remove-orphans --wait

prod-logs:
	$(COMPOSE_PROD) logs -f $(LOGS)

prod-logs-all:
	$(COMPOSE_PROD) logs -f --tail=100

prod-stop:
	$(COMPOSE_PROD) stop

prod-tag:
	docker tag opengsync-app:latest opengsync-app:$(CLEAN_VERSION)

deploy: prod-build prod-run
	docker system prune -f --filter "until=24h"

test:
	$(COMPOSE_TEST) down -v --remove-orphans
	$(COMPOSE_TEST) run --build --rm opengsync-pytest
	$(COMPOSE_TEST) down --remove-orphans -v

gitlab-runner:
	docker compose -f compose.gitlab-runner.yaml -p gitlab-runner up --build -d

gitlab-runner-stop:
	docker compose -f compose.gitlab-runner.yaml -p gitlab-runner down