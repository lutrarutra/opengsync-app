#!/bin/bash

docker compose --env-file=.env -f compose.yaml -p limbless-prod up --build "$@"