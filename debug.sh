#!/bin/bash
set -e

source .env
export OPENGSYNC_PORT=4999
docker compose -f compose.dev.yaml -p opengsync-dev up "$@" --remove-orphans