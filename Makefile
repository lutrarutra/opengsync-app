# Error: "*** missing separator." -> replace spaces with tabs

help:
	@echo "Error: Please specify a target."
	@echo "Usage: make [deploy|test|debug|prod-build|prod-run|prod-logs|prod-stop|dev-build|dev-run|dev-logs|dev-stop|gitlab-runner|gitlab-runner-stop]"
	@exit 1

.PHONY: dev-build dev-build-logs dev-run dev-attach dev-logs dev-logs-all dev-stop debug prod-build prod-build-logs prod-run prod-logs prod-logs-all prod-stop deploy test gitlab-runner gitlab-runner-stop

VERSION := $(shell git describe --tags --abbrev=0)
CLEAN_VERSION := $(shell echo $(VERSION) | sed 's/^v//')

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

prod-run:
	$(COMPOSE_PROD) up -d --remove-orphans --wait

prod-logs:
	$(COMPOSE_PROD) logs -f $(LOGS)

prod-logs-all:
	$(COMPOSE_PROD) logs -f

prod-stop:
	$(COMPOSE_PROD) stop

prod-tag:
	docker tag opengsync-app:latest opengsync-app:$(CLEAN_VERSION)

deploy: prod-build prod-run

test:
	$(COMPOSE_TEST) up --build --abort-on-container-exit --exit-code-from opengsync-pytest --remove-orphans && $(COMPOSE_TEST) down

gitlab-runner:
	docker compose -f compose.gitlab-runner.yaml -p gitlab-runner up --build -d

gitlab-runner-stop:
	docker compose -f compose.gitlab-runner.yaml -p gitlab-runner down