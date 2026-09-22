#!/bin/sh
# Runs a pgBackRest backup against the running Postgres container, then applies
# retention. Driven by the systemd timer in services/db/systemd/.
#
# Backups are executed inside the Postgres container on purpose:
#   * the pgBackRest binary, version, config, and PGBACKREST_* credentials are
#     exactly the ones archiving uses, which sidesteps the cross-host version
#     match pgBackRest otherwise requires;
#   * no repository credentials need to exist on the host or in this script.
#
# Retention (expire) runs after the backup so expired sets and the WAL they no
# longer need are removed in the same run. WAL required by any retained backup
# is preserved.
set -eu

CONTAINER="${PGBACKREST_CONTAINER:-postgres}"
STANZA="${PGBACKREST_STANZA:-opengsync}"

# Weekly full on Sunday (ISO day 7), differential every other day.
if [ "$(date +%u)" = "7" ]; then
    backup_type=full
else
    backup_type=diff
fi

echo "pgbackrest: starting ${backup_type} backup for stanza ${STANZA}"
# -u postgres: pgBackRest 2.59+ refuses to run as root for anything except
# restore (see the allow-root option), and running as root would also create
# repository/info files the postgres user cannot later read. The postmaster runs
# archive_command as postgres, so backups run the same way for consistency.
docker exec -u postgres "$CONTAINER" pgbackrest --stanza="$STANZA" backup --type="$backup_type"

echo "pgbackrest: applying retention"
docker exec -u postgres "$CONTAINER" pgbackrest --stanza="$STANZA" expire

echo "pgbackrest: ${backup_type} backup complete"
