#!/bin/bash

docker compose --env-file=.dev.env -f compose.dev.yaml -p limbless-dev up "$@"