# Production Deployment

## Prerequisites

- Docker and Docker Compose installed on the production server
- Git access to the repository

## Initial Setup

### 1. Clone the repository

```bash
git clone git@github.com:lutrarutra/opengsync-app.git /opt/opengsync
cd /opt/opengsync
git checkout fastapi
```

### 2. Create `.env` from template

```bash
cp templates/template.env .env
```

Edit `.env` and fill in **at minimum**:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Generate with `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | Database password |
| `PGBACKREST_REPO_DIR` | Host directory for database backups (see [Backup & Restore](#backup--restore)) |
| `MAIL_SERVER`, `MAIL_USER`, `MAIL_PASSWORD`, `MAIL_SENDER` | SMTP settings |

### 3. Create the Docker volumes

```bash
docker volume create opengsync-prod_postgres_data
docker volume create opengsync-prod_postgres_archive

# pgBackRest repository; owned by postgres in the image (uid/gid 70)
sudo install -d -o 70 -g 70 -m 750 "$PGBACKREST_REPO_DIR"
```

### 4. Pull images & start services

```bash
make prod-pull
make prod-run
```

### 5. Run database migrations

```bash
make prod-migrate
```

### 6. Verify everything

```bash
# Check services are running
docker compose -f compose.yaml ps
```

## Deploying Updates

Images are built and published to `ghcr.io/lutrarutra/opengsync-app/*` by the GitHub Actions workflow (`.github/workflows/images.yml`):

| Event | Tests | Images |
|---|---|---|
| Pull request into `main` | When backend inputs change | Changed images are built, not pushed |
| Push to `main` | — | — |
| Tag `vX.Y.Z` (new or force-moved) | When code changed since the previous release tag | Changed images rebuilt and pushed as `:vX.Y.Z`, `:latest` and `:sha-<short>`; unchanged images re-tagged from the previous release. Nothing moves if anything fails |

Every image therefore exists under every release tag. A re-tagged image still reports the version it was built as (the help page of a `v2.0.2` release whose backend did not change shows `2.0.1`).

Production pulls `:latest` (or `${APP_VERSION}`), so it only changes when a release tag is pushed.

Image tags match git tags (`v2.0.0`). To deploy a release on production, check out its tag; `make` sets `APP_VERSION` to it, so the compose file and the images come from the same release:

```bash
git fetch --tags
git checkout v2.0.0
make deploy
```

Off a tag, `APP_VERSION` from `.env` applies, falling back to `latest` (the newest release). `make deploy APP_VERSION=v2.0.1` overrides both. Rolling back means checking out the older tag and deploying again; database migrations are not rolled back automatically (see `make prod-downgrade`).

This runs `docker compose pull` followed by `docker compose up -d`, which restarts only services whose images changed.

## Backup & Restore

Backups use [pgBackRest](https://pgbackrest.org/) with two local repositories in the host directory `PGBACKREST_REPO_DIR`, which is bind-mounted into the `postgres` container at `/var/lib/pgbackrest` (`services/db/pgbackrest.conf`):

| Repository | Directory | Backups | Retention | Restores to |
|---|---|---|---|---|
| repo1 | `pitr/` | Full every Sunday | 31 days (plus the newest backup before that) | Any point in the last 31 days (in practice ~35–42) |
| repo2 | `monthly/` | Full on the first weekly run of each month | Forever | The moment each monthly backup was taken |

- **WAL archiving**: `archive_command` pushes every completed WAL segment (compressed) into both repositories (`services/db/postgresql.prod.conf`).
- **Backups and retention**: a systemd timer on the host runs `services/db/pgbackrest-backup.sh` every Sunday. It takes the repo1 backup, the repo2 backup if this month has none yet, and then runs `expire`. That removes repo1 backups older than the window, and in both repositories the WAL no retained backup needs. repo2 keeps continuous WAL only from its newest backup, so older months restore to their snapshot, not to points in between.
- **Growth**: repo1 stays roughly constant; repo2 grows by one compressed full backup per month, permanently.

Backups can only be restored with the PostgreSQL major version that made them. After a major upgrade, keep the last image tag of the old version to restore old monthly snapshots.

The repositories are on the same host, so they protect against corruption, mistakes and bad migrations, not against losing the host. Put `PGBACKREST_REPO_DIR` on a different disk than the Docker volumes if one is available, and copy it elsewhere (e.g. `rsync`) if off-host copies are needed.

### Setup

1. Create the repository directory and set it in `.env` (compose refuses to start without it):

   ```bash
   sudo install -d -o 70 -g 70 -m 750 /path/to/pgbackrest
   echo 'PGBACKREST_REPO_DIR=/path/to/pgbackrest' >> .env
   ```

2. Deploy the postgres image that contains the pgBackRest `archive_command` (`make deploy`). Until step 3 is done, every WAL push fails and PostgreSQL keeps the segments in `pg_wal` and retries, so do step 3 right away.

3. Create the stanza, verify archiving and take the first full backup:

   ```bash
   make prod-pgbackrest-init     # stanza-create + check (check forces a WAL switch and waits for it to be archived)
   make prod-pgbackrest-backup   # first backups (repo1 and this month's repo2)
   make prod-pgbackrest-info     # lists both repositories
   ```

   `SELECT * FROM pg_stat_archiver;` should show `failed_count` not increasing.

4. Install the weekly timer. Set `WorkingDirectory` and `ExecStart` (path to `services/db/pgbackrest-backup.sh`) in the service file, then:

   ```bash
   sudo cp services/db/systemd/paperplane-pgbackrest-backup.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now paperplane-pgbackrest-backup.timer
   systemctl list-timers paperplane-pgbackrest-backup.timer
   ```

5. The old `opengsync-prod_postgres_archive` volume (from the former `cp` archive_command) is no longer written to. Once the first pgBackRest full backup is older than 31 days, remove its mount from `compose.yaml` and delete the volume.

Watch `pg_stat_archiver.failed_count`, the size of `pg_wal`, the free space of `PGBACKREST_REPO_DIR` and failures of the systemd unit (`systemctl status paperplane-pgbackrest-backup.service`). A failing archiver fills the data volume until the cluster stops accepting writes.

### Restore (point in time)

Stop everything that writes to the database, then restore into the existing data volume (`--delta` only rewrites files that differ):

```bash
docker compose -f compose.yaml -p opengsync-prod stop opengsync-app opengsync-celery-worker opengsync-celery-beat postgres
docker compose -f compose.yaml -p opengsync-prod run --rm --no-deps -u postgres --entrypoint pgbackrest postgres \
    --stanza=opengsync --delta --type=time --target="2026-10-20 14:00:00+02" --target-action=promote restore
make prod-run
make prod-pgbackrest-backup   # new full backup on the new timeline
```

Omit `--type`, `--target` and `--target-action` to restore to the latest archived state.

### Restore a monthly snapshot

Find the backup label (e.g. `20251005-033012F`) with `make prod-pgbackrest-info`, then restore it from repo2. `--type=immediate` stops recovery as soon as the snapshot is consistent. Usually you want this in a scratch container (see below) rather than in production; in that case, replace the restore options there with these:

```bash
--stanza=opengsync --repo=2 --set=20251005-033012F --type=immediate --target-action=promote restore
```

### Test a restore

Restore into a scratch volume and start it with archiving off, so the test cluster never pushes WAL into the production repository (which is mounted read-only for the same reason):

```bash
IMAGE=ghcr.io/lutrarutra/opengsync-app/postgres:latest
docker volume create pgrestore-test
docker run --rm -u postgres -v pgrestore-test:/var/lib/postgresql/data -v "$PGBACKREST_REPO_DIR":/var/lib/pgbackrest:ro \
    --entrypoint pgbackrest "$IMAGE" --stanza=opengsync --type=time --target="2026-10-20 14:00:00+02" --target-action=promote restore
docker run -d --name pgrestore-test -v pgrestore-test:/var/lib/postgresql/data -v "$PGBACKREST_REPO_DIR":/var/lib/pgbackrest:ro \
    "$IMAGE" postgres -c config_file=/etc/postgresql.conf -c archive_mode=off
docker logs -f pgrestore-test   # wait for "database system is ready to accept connections"
docker exec -it pgrestore-test psql -U admin -d opengsync_db
docker rm -f pgrestore-test && docker volume rm pgrestore-test
```

## Service Reference

| Service | Image | Description |
|---|---|---|
| `db-migrator` | `ghcr.io/lutrarutra/opengsync-app/migrator` | Alembic migrations (one-shot) |
| `opengsync-app` | `ghcr.io/lutrarutra/opengsync-app/backend` | FastAPI application (gunicorn) |
| `opengsync-celery-worker` | `ghcr.io/lutrarutra/opengsync-app/worker` | Celery task worker |
| `opengsync-celery-beat` | `ghcr.io/lutrarutra/opengsync-app/worker` | Celery beat scheduler |
| `postgres` | `ghcr.io/lutrarutra/opengsync-app/postgres` | PostgreSQL + pgBackRest (WAL archiving, backups) |
| `nginx` | `ghcr.io/lutrarutra/opengsync-app/nginx` | Reverse proxy |
| `redis-cache` | `redis:8.0.3-alpine3.21` | Redis cache |
| `tailwind-compiler` | (built locally) | One-shot CSS compilation |
| `pgadmin` | `dpage/pgadmin4:latest` | Database admin UI (optional) |