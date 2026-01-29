#!/bin/bash
set -e

source .env
docker compose -f compose.dev.yaml -p opengsync-dev up "$@" --remove-orphans