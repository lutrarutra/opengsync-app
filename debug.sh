#!/bin/bash

if [ ! -f "./db/dev_postgres/postgresql.conf" ]; then
    echo "Copying templates/postgres/postgresql.conf to db/dev_postgres"
    cp ./templates/postgres/postgresql.conf ./db/dev_postgres
fi

if [ ! -f "rclone/rclone.conf" ]; then
    echo "Copy templates/rclone/rclone.conf to rclone/ and populate it."
    exit 1
fi

docker compose -f compose.dev.yaml -p limbless-dev up "$@"