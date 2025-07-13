#!/bin/bash

docker compose -f compose.test.yaml -p opengsync-testing up --abort-on-container-exit "$@"
STATUS=$?
docker compose -f compose.test.yaml -p opengsync-testing down --volumes

exit $STATUS
