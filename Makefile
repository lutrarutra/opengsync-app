# Error: "*** missing separator." -> replace spaces with tabs

VERSION := $(shell git describe --tags --abbrev=0)
OVERRIDE_FILE := $(wildcard compose.override.yaml)

# If OVERRIDE_FILE is not empty, add the -f flag
ifdef OVERRIDE_FILE
    OVERRIDE_FLAG := -f $(OVERRIDE_FILE)
else
    OVERRIDE_FLAG :=
endif

COMPOSE_DEV := docker compose -f compose.dev.yaml $(OVERRIDE_FLAG) -p opengsync-dev
COMPOSE_PROD := docker compose -f compose.yaml $(OVERRIDE_FLAG) -p opengsync-prod
COMPOSE_TEST := docker compose -f compose.test.yaml -p opengsync-test

dev-build:
	$(COMPOSE_DEV) build --build-arg VERSION=$(VERSION)

dev-build-logs:
	$(COMPOSE_DEV) build --progress=plain --build-arg VERSION=$(VERSION)

dev-run:
	$(COMPOSE_DEV) --env-file .env up -d --remove-orphans

dev-logs:
	$(COMPOSE_DEV) logs -f opengsync-app

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
	$(COMPOSE_PROD) --env-file .env up -d --remove-orphans --wait

prod-logs:
	$(COMPOSE_PROD) logs -f opengsync-app

prod-logs-all:
	$(COMPOSE_PROD) logs -f

prod-stop:
	$(COMPOSE_PROD) stop

deploy: prod-build prod-run

test:
	$(COMPOSE_TEST) up --build --abort-on-container-exit --exit-code-from opengsync-pytest --remove-orphans && $(COMPOSE_TEST) down

woodpecker:
	docker compose -f compose.woodpecker.yaml -p opengsync-ci up --build -d