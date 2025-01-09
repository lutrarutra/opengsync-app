#!/bin/bash

source .env
docker compose -f compose.dev.yaml -p limbless-dev up "$@"