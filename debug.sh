#!/bin/bash

docker compose -f compose.dev.yaml -p limbless-dev up "$@"