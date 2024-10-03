#!/bin/bash

psql postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public'" | grep -qw lims_user

if [ $? -eq 1 ] && [ "$LIMBLESS_TESTING" == 0 ]; then
    echo "Database does not exist. Creating database..."
    python3 init_db.py --create_users
fi

export TENX_MNT_POINT="/usr/src/app/mnt/sequences_10x"

mkdir -p $TENX_MNT_POINT
echo "Mounting: ${TENX_SEQUENCES_FOLDER} -> $TENX_MNT_POINT"
rclone mount cemm_cluster:${TENX_SEQUENCES_FOLDER} $TENX_MNT_POINT --dir-cache-time 5s \
    --poll-interval 10s --vfs-cache-mode full --read-only --cache-dir=/data/cache/0 --allow-non-empty --allow-other --daemon --log-file=/usr/src/app/logs/rclone.log

echo "$@"

if [ $? -eq 0 ]; then
    exec "$@"
else
    exit 1
fi