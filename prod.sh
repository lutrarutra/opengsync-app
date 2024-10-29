#!/bin/bash

if [ ! -f "rclone/rclone.conf" ]; then
    echo "Error: You must copy templates/rclone/rclone.conf to rclone/ and populate it."
    exit 1
fi

docker compose -f compose.yaml -p limbless-prod up --build "$@"