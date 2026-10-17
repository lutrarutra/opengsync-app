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
| `MAIL_SERVER`, `MAIL_USER`, `MAIL_PASSWORD`, `MAIL_SENDER` | SMTP settings |

### 3. Create the Docker volumes

```bash
docker volume create opengsync-prod_postgres_data
docker volume create opengsync-prod_postgres_archive
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
| Push to `main` | When backend inputs change | Changed images pushed as `:main` and `:sha-<short>` |
| Tag `vX.Y.Z` | Always | All images pushed as `:vX.Y.Z` and `:latest`, only if tests pass |

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

WAL archiving copies every completed WAL segment into the `opengsync-prod_postgres_archive` volume (`archive_command = 'cp %p /var/lib/postgresql/archive/%f'` in `services/db/postgresql.prod.conf`). Nothing prunes this volume, so watch its size.

pgBackRest is currently **disabled**: no backup repository is configured. The pgBackRest binary, `services/db/pgbackrest.conf`, `services/db/pgbackrest-backup.sh` and the systemd units are kept so it can be re-enabled once a repository (e.g. SFTP or S3) is available.

## Service Reference

| Service | Image | Description |
|---|---|---|
| `db-migrator` | `ghcr.io/lutrarutra/opengsync-app/migrator` | Alembic migrations (one-shot) |
| `opengsync-app` | `ghcr.io/lutrarutra/opengsync-app/backend` | FastAPI application (gunicorn) |
| `opengsync-celery-worker` | `ghcr.io/lutrarutra/opengsync-app/worker` | Celery task worker |
| `opengsync-celery-beat` | `ghcr.io/lutrarutra/opengsync-app/worker` | Celery beat scheduler |
| `postgres` | `ghcr.io/lutrarutra/opengsync-app/postgres` | PostgreSQL (pgBackRest installed, currently disabled) |
| `nginx` | `ghcr.io/lutrarutra/opengsync-app/nginx` | Reverse proxy |
| `redis-cache` | `redis:8.0.3-alpine3.21` | Redis cache |
| `tailwind-compiler` | (built locally) | One-shot CSS compilation |
| `pgadmin` | `dpage/pgadmin4:latest` | Database admin UI (optional) |