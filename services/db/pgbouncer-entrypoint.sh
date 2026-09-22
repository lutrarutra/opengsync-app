#!/bin/sh
# Renders the runtime PgBouncer config from the environment, then execs
# pgbouncer.
#
# Three things are rendered here rather than committed:
#   * the client userlist, so the database password stays out of git;
#   * the [databases] section, so the backend host/port follow DB_HOST/DB_PORT
#     instead of being duplicated in the read-only pgbouncer.ini mount;
#   * stats_users, so the read-only console user that pgbouncer_exporter
#     connects as is deployment-specific rather than baked into the file.
set -eu

# Materialize Swarm secret files into environment variables, so DB_PASSWORD can
# come from a mounted secret instead of the service spec. Mount targets are
# named after the variables they feed (see stack.prod.yaml). An explicit
# environment variable still wins. Kept identical to services/db/entrypoint.sh;
# it is duplicated rather than shared because this script is baked into one
# image and that one into another.
if [ -d /run/secrets ]; then
    for secret_file in /run/secrets/*; do
        [ -f "$secret_file" ] || continue
        secret_name=$(basename "$secret_file")
        case "$secret_name" in
            '' | [0-9]* | *[!A-Za-z0-9_]*)
                echo "entrypoint: ignoring secret '$secret_name': not a valid environment variable name" >&2
                continue
                ;;
        esac
        if [ -n "$(printenv "$secret_name" 2>/dev/null || true)" ]; then
            continue
        fi
        export "$secret_name=$(cat "$secret_file")"
    done
fi

: "${DB_HOST:?DB_HOST is required}"
: "${DB_PORT:=5432}"
: "${DB_USER:?DB_USER is required}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"

# Monitoring is optional here on purpose. PgBouncer works fine without a console
# user, and a deployment that has not configured monitoring (stack.prod.yaml, for
# instance) should not fail to start because of it. When the variables are
# absent the console stays closed to everyone, which is pgbouncer's default.
if [ -n "${STATS_USER:-}" ]; then
    : "${STATS_PASSWORD:?STATS_PASSWORD is required once STATS_USER is set}"

    # STATS_USER is spliced into the rendered config with sed, so keep it to
    # characters that cannot be read as part of a sed expression. Usernames are
    # plain identifiers in practice; reject anything else loudly rather than
    # emitting a config pgbouncer will refuse to parse.
    case "$STATS_USER" in
        '' | [0-9]* | *[!A-Za-z0-9_]*)
            echo "entrypoint: STATS_USER '$STATS_USER' is not a plain identifier" >&2
            exit 1
            ;;
    esac
fi

src_ini="${PGBOUNCER_CONFIG:-/etc/pgbouncer/pgbouncer.ini}"
runtime_dir="${PGBOUNCER_RUNTIME_DIR:-/tmp/pgbouncer}"
mkdir -p "$runtime_dir"
# PgBouncer drops privileges to `user = postgres`, so it must be able to read
# the rendered config and userlist and write its pidfile in here.
chmod 1777 "$runtime_dir"

# Plain-text entries are accepted for auth_type = scram-sha-256.
printf '"%s" "%s"\n' "$DB_USER" "$DB_PASSWORD" > "$runtime_dir/userlist.txt"

# The console user does not exist in PostgreSQL: the console is a virtual
# database served entirely by PgBouncer, so it needs an entry here and a
# stats_users mention below - nothing else.
if [ -n "${STATS_USER:-}" ]; then
    printf '"%s" "%s"\n' "$STATS_USER" "$STATS_PASSWORD" >> "$runtime_dir/userlist.txt"
fi

{
    printf '[databases]\n'
    printf '* = host=%s port=%s\n\n' "$DB_HOST" "$DB_PORT"
    if [ -n "${STATS_USER:-}" ]; then
        # stats_users is the only value inside pgbouncer.ini that must be
        # rendered. The committed file carries a placeholder so this stays a
        # plain string substitution: inserting a line into the correct section
        # would instead depend on section ordering, which is invisible and easy
        # to break.
        sed "s/__PGBOUNCER_STATS_USERS__/$STATS_USER/" "$src_ini"
    else
        # No monitoring configured: drop the line entirely so pgbouncer keeps
        # its default, a console no user can log in to.
        sed "/__PGBOUNCER_STATS_USERS__/d" "$src_ini"
    fi
} > "$runtime_dir/pgbouncer.ini"

exec pgbouncer "$runtime_dir/pgbouncer.ini"
