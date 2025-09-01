#!/bin/bash

source .env
docker compose -f compose.yaml -p opengsync-prod down --volumes --remove-orphans
docker compose -f compose.yaml -p opengsync-prod up --build "$@"