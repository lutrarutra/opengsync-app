#!/bin/bash
set -e

source .env
uv sync
docker compose -f compose.dev.yaml -p opengsync-dev up "$@"