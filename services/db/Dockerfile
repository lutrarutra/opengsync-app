# --- Postgres with pgBackRest ---
#
# pgBackRest must be present on the database host: PostgreSQL invokes
# `archive_command` for every completed WAL segment, and that command is
# pgBackRest's archive-push. Scheduled operations (backup/expire/check) are run
# against the same container so they use the identical binary and config.
#
# The base stays Alpine on purpose. The existing production cluster was
# initialized under musl (postgres:17-alpine); moving the same data directory
# under a glibc-based image can change collation behavior, so the base is not
# swapped for the sake of an apt package.
#
# pgBackRest comes from the stable Alpine community repo of the base image. The
# Alpine release is pinned in the base tag so the available pgBackRest version
# only changes when the tag is bumped deliberately, and the version is pinned to
# a minor release (`~`) so patch updates within that release still resolve.
# (edge/community is not used: it only keeps the newest build of each package,
# so an exact pin there breaks as soon as edge moves on.)
ARG PGBACKREST_VERSION=2.58

FROM postgres:17-alpine3.24

ARG PGBACKREST_VERSION

RUN apk add --no-cache \
      "pgbackrest~${PGBACKREST_VERSION}" \
      openssh-client \
    && mkdir -p /etc/pgbackrest /var/log/pgbackrest /var/lib/pgbackrest /var/spool/pgbackrest \
    && chown -R postgres:postgres /var/log/pgbackrest /var/lib/pgbackrest /var/spool/pgbackrest \
    && pgbackrest version

# Wrapper that exports Swarm secret files as environment variables before
# delegating to the official entrypoint. Baked into the image rather than
# mounted, because Swarm cannot bind-mount a single host file.
COPY services/db/entrypoint.sh /usr/local/bin/opengsync-entrypoint.sh
RUN chmod +x /usr/local/bin/opengsync-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/opengsync-entrypoint.sh"]

