#!/bin/bash

docker compose --env-file=.prod.env -f compose.yaml -p limbless-prod up --build "$@"