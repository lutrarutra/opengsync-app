#!/bin/bash
set -euo pipefail

source /etc/environment
echo "${POSTGRES_HOST}:${POSTGRES_PORT}:${POSTGRES_DB}:${POSTGRES_USER}:${POSTGRES_PASSWORD}" > /root/.pgpass && chmod 600 /root/.pgpass

export PGPASSFILE="/root/.pgpass"
export PGPASSWORD="${POSTGRES_PASSWORD}"
DATETIME="$(date +%Y%m%d_%H%M)"

echo "Creating logical dump..."
pg_dump -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -p 5432 -F c -f /backups/dump/"$DATETIME".dump "${POSTGRES_DB}"

echo "Creating base backup..."
pg_basebackup -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -p 5432 -D /backups/base/"$DATETIME" -P -Xs
tar -cvf /backups/base/"$DATETIME".tar.gz -C /backups/base "$DATETIME"
rm -rf /backups/base/"$DATETIME"

echo "Backup completed: $DATETIME"