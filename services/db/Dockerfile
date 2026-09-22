# --- Postgres with pgBackRest ---
#
# pgBackRest must be present on the database host: PostgreSQL invokes
# `archive_command` for every completed WAL segment, and that command is
# pgBackRest's archive-push. Scheduled operations (backup/expire/check) are run
# against the same container so they use the identical binary and config.
#
# The base stays Alpine on purpose. The existing production cluster was
# initialized under musl (postgres:18-alpine); moving the same data directory
# under a glibc-based image can change collation behavior, so the base is not
# swapped for the sake of an apt package.
#
# The version is pinned because pgBackRest requires identical versions on every
# host that touches the repository.
ARG PGBACKREST_VERSION=2.59.1-r0

FROM postgres:17-alpine

ARG PGBACKREST_VERSION

# pgBackRest is not in the stable Alpine repos, so it comes from edge/community.
# The repository is passed per-install rather than appended to
# /etc/apk/repositories: adding it globally would let a later `apk upgrade` pull
# edge versions of shared libraries into the database image.
RUN apk add --no-cache \
      --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community \
      "pgbackrest=${PGBACKREST_VERSION}" \
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

