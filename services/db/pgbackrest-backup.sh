#!/bin/sh
# Weekly pgBackRest run against the running Postgres container, driven by the
# systemd timer in services/db/systemd/ (or `make prod-pgbackrest-backup`):
#
#   1. full backup to repo1 (PITR, 31-day retention);
#   2. full backup to repo2 (monthly snapshot, kept forever) if repo2 has none
#      from the current month yet - so the first run of each month takes it,
#      and a missed run is caught up by the next one;
#   3. expire, which applies each repository's retention (see pgbackrest.conf).
#
# Backups are executed inside the Postgres container on purpose:
#   * the pgBackRest binary, version and config are exactly the ones archiving
#     uses, which sidesteps the cross-host version match pgBackRest otherwise
#     requires;
#   * the repositories are only mounted into that container.
set -eu

CONTAINER="${PGBACKREST_CONTAINER:-postgres}"
STANZA="${PGBACKREST_STANZA:-opengsync}"

# -u postgres: pgBackRest 2.59+ refuses to run as root for anything except
# restore (see the allow-root option), and running as root would also create
# repository files the postgres user (which runs archive_command) cannot later
# read or remove.
pgbackrest() {
    docker exec -u postgres "$CONTAINER" pgbackrest --stanza="$STANZA" "$@"
}

echo "pgbackrest: full backup to repo1 (pitr)"
pgbackrest --repo=1 backup --type=full

# Backup labels start with the backup's start date (YYYYMMDD-HHMMSSF), and
# `info` lists them oldest first, so the last one is the newest. Captured before
# parsing so a failing `info` stops the script instead of reading as "no backup".
repo2_info=$(pgbackrest --repo=2 info --output=json)
last_month=$(printf '%s' "$repo2_info" \
    | grep -o '"label":"[0-9]\{8\}-[0-9]\{6\}F"' \
    | tail -n 1 \
    | cut -c 10-15)

if [ "$last_month" = "$(date +%Y%m)" ]; then
    echo "pgbackrest: repo2 (monthly) already has a backup from this month"
else
    echo "pgbackrest: full backup to repo2 (monthly)"
    pgbackrest --repo=2 backup --type=full
fi

echo "pgbackrest: applying retention"
pgbackrest expire

echo "pgbackrest: done"
