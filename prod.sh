#!/bin/bash

docker compose -f compose.yaml -p limbless-prod up --build "$@"