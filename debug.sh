#!/bin/bash

source .env
docker compose -f compose.dev.yaml -p opengsync-dev up "$@"