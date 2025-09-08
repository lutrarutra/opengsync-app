#!/bin/bash

cd <repository path>
source .env

if [ -f "compose.override.yaml" ]; then
    docker compose -f compose.yaml -f compose.override.yaml -p opengsync-prod "$@"
else
    docker compose -f compose.yaml -p opengsync-prod "$@"
fi