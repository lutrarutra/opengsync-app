# Limbless
Web app for NGS sample/library/project tracking

# Containers
1. `limbless-app` - Flask web server
1. `limbless-db` - PostgreSQL database
1. `rf-scanenr` - Illumina run folder scanner
1. `ofelia` - `Scheduled temporary file cleaner`
    - Production only
1. `nginx` - Reverse proxy for static files
    - Production only
1. `pgadmin` - PostgreSQL admin interface
1. `yacht` - Web interface for managing docker containers
1. `sass-compiler` - Compiles scss to css
1. `redis` - Cache for Flask app

# Directories
1. `templates` - Templates for configuration files `tracked ✅`
1. `media` - long term storage for files
1. `uploads` - short term storage for temporary files
1. `logs` - Log files
1. `backup` - Backup of database
1. `cert` - SSL certificates
1. `rclone` - rclone configuration
1. `cache` - Cache for Flask app
1. `db` - Database files

# Production Server service

## Initial Setup
- `cp templates/template.env .env`
    - Populate .env as required.
- `mkdir rclone && cp templates/rclone.conf rclone/`
    - Populate rclone/rclone.conf as required.
- `mkdir db/pgadmin && sudo chown -R 5050:5050 db/pgadmin`

## Start Production Server (2 options)

### 1. Start production server as systemd service
- `sudo cp templates/limbless.service /lib/systemd/system/limbless.service`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable limbless`
- `sudo systemctl start limbless`

#### Logs
- View
    - `sudo journalctl -u limbless -e`
- Stream
    - `sudo journalctl -u limbless -e -f`
#### Check service status
- `sudo systemctl status limbless`
#### Restart service (e.g. update)
- `sudo systemctl restart limbless`

### 2. Or run production server
- `chmod +x prod.sh`
- `./prod.sh` 


# Setup for Development

* ✅ Hot reload python files on change.
* ✅ Compilation of scss files on change.

```bash
pip install -r services/limbless-app/limbless-db/requirements.txt
pip install -e services/limbless-app/limbless-db
pip install -r services/limbless-app/limbless-server/requirements.txt
pip install -e services/limbless-app/limbless-server
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
- host: `postgres` & port: `5432` (prod) `5433` (dev) or
- Find the IP address of the container:
    1. `docker ps`
    2. `docker inspect limbless-postgres-db | grep IPAddress`
- username: `$(POSTGRES_USER)`
- password: `$(POSTGRES_PASSWORD)`