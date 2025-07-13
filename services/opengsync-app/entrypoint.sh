#!/bin/bash

# psql postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public'" | grep -qw lims_user

if [ $? -eq 0 ]; then
    python3 /usr/src/app/debug.py --host=0.0.0.0 --port=${OPENGSYNC_PORT}
else
    exit 1
fi