#!/bin/bash

if [ ! -f "rclone/rclone.conf" ]; then
    echo "Copy templates/rclone/rclone.conf to rclone/ and populate it."
    exit 1
fi

source .env

docker compose -f compose.dev.yaml -p limbless-dev up "$@"