#!/bin/bash

rm -rf .tmp/
docker compose --env-file=.test.env -f compose.test.yaml -p limbless-testing up --abort-on-container-exit "$@"
rm -rf .tmp/
