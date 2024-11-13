#!/bin/bash

docker compose -f compose.test.yaml -p limbless-testing up --abort-on-container-exit "$@"
STATUS=$?
docker compose -f compose.test.yaml -p limbless-testing down --volumes

exit $(STATUS)
