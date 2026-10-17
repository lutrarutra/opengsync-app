#!/bin/sh
# Entrypoint wrapper for the database image.
#
# Its only job is to turn Swarm secret *files* into environment variables before
# handing off to the official postgres entrypoint, then let that entrypoint do
# initdb / init.sh / exec postgres as usual.
#
# Why a wrapper is needed at all:
#   * Swarm mounts every secret as a read-only file under /run/secrets, because
#     that is the only way to hand a secret to a container without putting it in
#     the service spec (where `docker service inspect` would show it);
#   * pgBackRest has no `*-file` option - its credentials can only come from the
#     command line, the config file, or the environment - so the values have to
#     be read from disk and exported;
#   * the archive_command runs as a child of the postmaster, which inherits the
#     environment of `postgres`, so anything exported here reaches pgBackRest.
#
# Names are taken from the *mount target* of each secret, not the Swarm object
# name, so compose can map `postgres_admin_password` onto POSTGRES_PASSWORD.
set -eu

# Export every file under /run/secrets under a name that matches its filename.
# Skipped names are reported rather than ignored: a secret that silently fails
# to load would surface much later, as a failed backup or a broken login.
load_secrets() {
    [ -d /run/secrets ] || return 0
    for secret_file in /run/secrets/*; do
        # Guard against the literal glob when the directory is empty.
        [ -f "$secret_file" ] || continue
        secret_name=$(basename "$secret_file")

        case "$secret_name" in
            '' | [0-9]* | *[!A-Za-z0-9_]*)
                echo "entrypoint: ignoring secret '$secret_name': not a valid environment variable name" >&2
                continue
                ;;
        esac

        # An explicit environment variable wins over the secret file, so the
        # precedence matches the rest of the system (and `docker run -e` can
        # still override for debugging). `printenv` is used instead of eval so
        # the secret name is never interpreted as shell syntax.
        if [ -n "$(printenv "$secret_name" 2>/dev/null || true)" ]; then
            continue
        fi

        # Command substitution strips trailing newlines, which is what we want:
        # a secret created with `echo` would otherwise carry a trailing \n into
        # the password. Internal newlines are preserved.
        secret_value=$(cat "$secret_file")
        export "$secret_name=$secret_value"
    done
}

load_secrets

# pgBackRest locates the cluster through pg1-path. Derive it from PGDATA rather
# than hardcoding it: the official image moved PGDATA in PostgreSQL 18
# (/var/lib/postgresql/data -> /var/lib/postgresql/18/docker) and moves it again
# on every major version. A stale pg1-path points pgBackRest at an empty
# directory, which surfaces as `[056] unable to find primary cluster` on
# stanza-create and as a permanently failing archiver otherwise - and a failing
# archiver fills pg_wal until the cluster stops accepting writes.
#
# The environment wins over the config file, so this overrides the [opengsync]
# pg1-path fallback.
if [ -z "${PGBACKREST_PG1_PATH:-}" ] && [ -n "${PGDATA:-}" ]; then
    export PGBACKREST_PG1_PATH="$PGDATA"
fi

# exec so the postmaster replaces this shell and keeps receiving signals; the
# official entrypoint is what performs initdb and then `exec postgres`.
exec docker-entrypoint.sh "$@"
