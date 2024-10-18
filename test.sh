#!/bin/bash

docker compose -f compose.test.yaml -p limbless-testing up --abort-on-container-exit "$@"
docker compose -f compose.test.yaml -p limbless-testing down --volumes
