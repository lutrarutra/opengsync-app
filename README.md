# OpeNGSync
Web app for NGS sample/library/project tracking

# Containers
1. `opengsync-app` - Flask web server @ `https://localhost:80`
1. `opengsync-db` - PostgreSQL database
1. `scheduler` - Scheduler for running scheduled tasks in python: old file cleaning, status updates, and run-folder scanner
1. `nginx` - Reverse proxy for static files (only prod)
1. `pgadmin` - PostgreSQL admin interface @ `https://localhost:5050`
1. `yacht` - Web interface for managing docker containers @ `https://localhost:8000`
1. `sass-compiler` - Compiles scss to css
1. `redis` - Cache for Flask app

# Directories
1. `templates` - Templates for configuration files `tracked ✅`
1. `media` - long term storage for files
1. `uploads` - short term storage for temporary files
1. `logs` - Log files
1. `backup` - Backup of database
1. `cert` - SSL certificates
1. `cache` - Cache for Flask app
1. `db` - Database files

# Production Server service

## Initial Setup
- `cp templates/template.env .env`
    - Populate .env as required.
- `mkdir -p db/pgadmin && sudo chown -R 5050:5050 db/pgadmin`
- `mkdir -p db/postgres && sudo chown -R 999:999 db/postgres`
- `mkdir -p data/db_backup/wal && sudo chown -R 999:999 data/db_backup/wal`

## Start Production Server (2 options)

### 1. Start production server as systemd service
- `sudo cp templates/opengsync.service /lib/systemd/system/opengsync.service`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable opengsync`
- `sudo systemctl start opengsync`

#### Logs
- View
    - `sudo journalctl -u opengsync -e`
- Stream
    - `sudo journalctl -u opengsync -e -f`
#### Check service status
- `sudo systemctl status opengsync`
#### Restart service (e.g. update)
- `sudo systemctl restart opengsync`

### Update
- `prod-update.sh`
    1. Creates temporary testing environment
    1. Runs unit tests
    1. If tests pass, pulls from git
    1. Rebuilds containers
    1. Restarts service (systemctl)

### 2. Or run production server
- `chmod +x prod.sh`
- `./prod.sh` 

## After first boot
- Change yacht login and password
    - `http://localhost:${YACHT_PORT}`
    - default username: `admin@yacht.local`
    - default password: `pass`


# Setup for Development (virtual/conda environment recommended)

* ✅ Hot reload python files on change.
* ✅ Compilation of scss files on change.

```bash
pip install -e services/opengsync-app/opengsync-db
pip install -e services/opengsync-app/opengsync-server
mkdir db/dev_pgadmin
sudo chown -R 5050:5050 db/dev_pgadmin
```

## Run with flask debug server
- `chmod +x debug.sh`
- `./debug.sh --build`
## Unit tests
- `chmod +x test.sh`
- `./test.sh`

## pgAdmin Interface
- `http://localhost:${PGADMIN_PORT}`
- username: `$(PGADMIN_EMAIL)`
- password: `$(PGADMIN_PASSWORD)`

## pgAdmin Server Setup
- host: `postgres` & port: `$(POSTGRES_PORT)` or
- Find the IP address of the container:
    1. `docker ps`
    2. `docker inspect opengsync-postgres-db | grep IPAddress`
- username: `$(POSTGRES_USER)`
- password: `$(POSTGRES_PASSWORD)`


# Unit Tests
- `chmod +x test.sh`
- `./test.sh --build`

## Tests
- SQL Database models, links
- Common library prep table requirements


