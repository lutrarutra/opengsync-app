# Production Deployment

## Prerequisites

- Docker and Docker Compose installed on the production server
- Git access to the repository
- A backup server with SSH access for pgBackRest

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
| `PGBACKREST_REPO1_HOST` | Backup server hostname/IP |
| `PGBACKREST_SSH_KEY` | Path to SSH key on the host (e.g. `./secrets/pgbackrest_id_ed25519`) |

### 3. Set up SSH key for pgBackRest

Generate a key pair on the production server:

```bash
mkdir -p secrets
ssh-keygen -t ed25519 -f ./secrets/pgbackrest_id_ed25519 -N ""
```

Install the public key on the backup server:

```bash
ssh-copy-id -i ./secrets/pgbackrest_id_ed25519.pub pgbackrest@<backup-server>
```

Create the known_hosts file:

```bash
ssh-keyscan <backup-server> > ./secrets/pgbackrest_known_hosts
```

### 4. Create the Docker volume

```bash
docker volume create opengsync-prod_postgres_data
```

### 5. Pull images & start services

```bash
make prod-pull
make prod-run
```

### 6. Run database migrations

```bash
make prod-migrate
```

### 7. Initialize pgBackRest stanza

```bash
docker exec -u postgres postgres pgbackrest --stanza=opengsync stanza-create
docker exec -u postgres postgres pgbackrest --stanza=opengsync check
```

### 8. Set up the systemd backup timer

Edit `services/db/systemd/paperplane-pgbackrest-backup.service` and replace `<changeme>` with your actual paths:

```ini
WorkingDirectory=/opt/opengsync
ExecStart=/opt/opengsync/services/db/pgbackrest-backup.sh
```

Then install and start the timer:

```bash
sudo cp services/db/systemd/paperplane-pgbackrest-backup.service /etc/systemd/system/
sudo cp services/db/systemd/paperplane-pgbackrest-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now paperplane-pgbackrest-backup.timer
```

### 9. Verify everything

```bash
# Check services are running
docker compose -f compose.yaml ps

# Check pgBackRest
docker exec -u postgres postgres pgbackrest --stanza=opengsync info

# Check backup timer
sudo systemctl status paperplane-pgbackrest-backup.timer
```

## Deploying Updates

Images are built and published to `ghcr.io/lutrarutra/opengsync-app/*` by the GitHub Actions workflow (`.github/workflows/images.yml`) on every push to `main` or `fastapi`.

To deploy the latest images on production:

```bash
make deploy
```

This runs `docker compose pull` followed by `docker compose up -d`, which restarts only services whose images changed.

## Backup & Restore

### Backup schedule

- **Daily at 03:30** — full backup on Sunday, differential on other days
- **WAL archiving** — continuous, every WAL segment is pushed to the backup server in real-time
- **Retention** — 2 weekly fulls kept, WAL retained 30 days beyond the oldest full (~44 days PITR)

### Manual backup

```bash
docker exec -u postgres postgres pgbackrest --stanza=opengsync backup --type=full
```

### List available backups

```bash
docker exec -u postgres postgres pgbackrest --stanza=opengsync info
```

### Restore

See [pgBackRest documentation](https://pgbackrest.org/) for restore procedures.

## Service Reference

| Service | Image | Description |
|---|---|---|
| `db-migrator` | `ghcr.io/lutrarutra/opengsync-app/migrator` | Alembic migrations (one-shot) |
| `opengsync-app` | `ghcr.io/lutrarutra/opengsync-app/backend` | FastAPI application (gunicorn) |
| `opengsync-celery-worker` | `ghcr.io/lutrarutra/opengsync-app/worker` | Celery task worker |
| `opengsync-celery-beat` | `ghcr.io/lutrarutra/opengsync-app/worker` | Celery beat scheduler |
| `postgres` | `ghcr.io/lutrarutra/opengsync-app/postgres` | PostgreSQL with pgBackRest |
| `nginx` | `ghcr.io/lutrarutra/opengsync-app/nginx` | Reverse proxy |
| `redis-cache` | `redis:8.0.3-alpine3.21` | Redis cache |
| `tailwind-compiler` | (built locally) | One-shot CSS compilation |
| `pgadmin` | `dpage/pgadmin4:latest` | Database admin UI (optional) |