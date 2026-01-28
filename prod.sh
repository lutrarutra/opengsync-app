#!/bin/bash
set -e

source .env

if [ -z "$USER" ] || [ "$USER" -eq 0 ]; then
    USER=$(id -u)
fi

if [ -z "$GROUP" ] || [ "$GROUP" -eq 0 ]; then
    GROUP=$(id -g)
fi

if [ -f "compose.override.yaml" ]; then
    docker compose -f compose.yaml -f compose.override.yaml -p opengsync-prod up --build "$@"
else
    docker compose -f compose.yaml -p opengsync-prod up --build "$@"
fi
