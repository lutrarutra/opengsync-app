#!/bin/bash
source .dev.env
docker compose -f compose.dev.yaml -p limbless-debug up "$@"