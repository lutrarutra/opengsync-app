#!/bin/bash

source .env
docker compose -f compose.yaml -p limbless-prod up --build "$@"