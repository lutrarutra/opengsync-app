#!/bin/bash

docker compose --env-file=.env -f compose.dev.yaml -p limbless-dev up "$@"