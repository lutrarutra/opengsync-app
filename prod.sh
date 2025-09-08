#!/bin/bash

source .env

if [ -f "compose.override.yaml" ]; then
    docker compose -f compose.yaml -f compose.override.yaml -p opengsync-prod down --volumes --remove-orphans
    docker compose -f compose.yaml -f compose.override.yaml -p opengsync-prod up --build "$@"
else
    docker compose -f compose.yaml -p opengsync-prod down --volumes --remove-orphans
    docker compose -f compose.yaml -p opengsync-prod up --build "$@"
fi
