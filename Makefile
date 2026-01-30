# Error: "*** missing separator." -> replace spaces with tabs

VERSION := $(shell git describe --tags --always)
COMPOSE_DEV := docker compose -p opengsync-dev -f compose.dev.yaml

dev-build:
	$(COMPOSE_DEV) build --build-arg VERSION=$(VERSION)

dev-build-logs:
	$(COMPOSE_DEV) build --progress=plain --build-arg VERSION=$(VERSION)

dev-run:
	$(COMPOSE_DEV) up -d

dev-logs:
	$(COMPOSE_DEV) logs -f opengsync-app

dev-logs-all:
	$(COMPOSE_DEV) logs -f

dev-stop:
	$(COMPOSE_DEV) stop

debug: dev-build dev-run dev-logs