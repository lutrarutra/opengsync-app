#!/bin/bash

psql postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public'" | grep -qw lims_user

if [ $? -eq 1 ] && [ "$LIMBLESS_TESTING" != 0 ]; then
    echo "Database does not exist. Creating database..."
    python3 init_db.py --create_users --add_kits
fi


if [ $? -eq 0 ]; then
    exec "$@"
else
    exit 1
fi