# OpeNGSync
Modern web app for NGS sample/library/project tracking and NGS service request management.

## Features
* Create validated sample annotation sheets
* Track sample, library, project, and sequencing statuses
* Store QC data
* Share data securely with customers
* Track used reagents, kits, and software
* User roles, and permissions
* Generate reports and plotting/visualizing statistics

## Tech Stack
1. `opengsync-app` - Flask web server @ `https://localhost:80`
1. `opengsync-db` - PostgreSQL database
1. `scheduler` - Custom python container for running scheduled tasks: old file cleaning, status updates, and run-folder scanner
1. `nginx` - Reverse proxy for static files (only prod)
1. `pgadmin` - PostgreSQL admin interface @ `https://localhost:5050`
1. `yacht` - Web interface for overview of running docker containers @ `https://localhost:8000`
1. `sass-compiler` - Compiles scss to css
1. `redis` - Cache for Flask app

## Performance Considerations
- Gunicorn with multiple workers
- Nginx reverse proxy for serving static files
- Route response caching in memory
- Page modularization and lazy loading with `HTMX`
- DB connection pools

## Directories
1. `templates` - Templates for configuration files `tracked ✅`
1. `media` - long term storage for uploaded media (pdf/excel/images/etc..) files
1. `uploads` - short term storage for temporary files
1. `logs` - Log files
1. `backup` - Backup of database
1. `cert` - SSL certificates
1. `cache` - Cache for Flask app
1. `db` - Database files

# Production Server service

## Initial Setup

### 1. Create folders with correct permissions
- `cp templates/template.env .env`
    - Populate .env as required.

```sh
mkdir -p db
mkdir -p db/pgadmin && sudo chown -R 5050:5050 db/pgadmin
mkdir -p db/postgres && sudo chown -R 999:999 db/postgres
mkdir -p data/db_backup/wal && sudo chown -R 999:999 data/db_backup/wal
mkdir -p data/db_backup/base && sudo chown -R 999:999 data/db_backup/base
```

### 2. Start production server as systemd service
```sh
sudo cp templates/opengsync.service /lib/systemd/system/opengsync.service
sudo systemctl daemon-reload
sudo systemctl enable opengsync
sudo systemctl start opengsync
```
or
`./prod.sh`

- Wait for startup: `sudo journalctl -u opengsync -e -f`

### 3. Create Base Backup
```sh
# host
docker exec -it postgres sh
# In postgres container 
pg_basebackup \
  -U <user> \
  -D /var/lib/postgresql/base \
  -F tar \
  -X fetch \
  -P
```

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
- `update.sh`
    1. Creates temporary testing environment
    1. Runs unit tests
    1. If tests pass, pulls from git
    1. Rebuilds containers
    1. Restarts service (`systemctl`)

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
mkdir -p db
mkdir -p db/pgadmin && sudo chown -R 5050:5050 db/pgadmin
mkdir -p db/postgres && sudo chown -R 999:999 db/postgres
mkdir -p data/db_backup/wal && sudo chown -R 999:999 data/db_backup/wal
mkdir -p data/db_backup/base && sudo chown -R 999:999 data/db_backup/base
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


# Share

## Download shared file:
```sh
rclone copy --http-url http://<ip>/api/files/browse/<token> :http: . -v --stats-log-level NOTICE --stats 500ms --progress
```

# ORM Database
```python
db = DBHandler()
db.connect(
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_SERVER_IP"],
    port=os.environ["POSTGRES_PORT"],
    db=os.environ["POSTGRES_DB"],
)
```

- When reading/writing data from/to db, db session must be opened: `db.open_session()`
- If session is closed (and `auto_open=False`), querying the database will raise `sqlalchemy.orm.exc.DetachedInstanceError`.
- If `auto_open=True` when creating `DBHandler`-object, session is opened and closed automatically. But lazy loading of relationships will not work.
- `db.close_session()` writes/commits the updates to db and closes the session.

### Jupyter/IPython Auto DB Session Open Extension
When working in Jupyer Notebook, you can enable autosession extension which will open and close db session automatically when running a cell.
```python
from opengsync_db.ext.autosession import set_db
%load_ext opengsync_db.ext.autosession

db = DBHandler()
db.connect(
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_SERVER_IP"],
    port=os.environ["POSTGRES_PORT"],
    db=os.environ["POSTGRES_DB"],
)
set_db(db)  # Important
```

## DB API
### Pandas DataFrame
- User one of the pre-existing queries, e.g:
    - `db.pd.get_project_libraries(project_id)`
    - `db.pd.get_seq_requestor(seq_request_id)`
- Or custom query:
```python
# Custom query
db.pd.query(sa.select(models.Library).order_by(models.Library.status_id, models.Library.id).limit(5))
# Equivalent to
db.pd.query("SELECT * FROM library ORDER BY status_id, id LIMIT 5")
```

### ORM Models

#### Sub-modules
```python
db.seq_requests
db.libraries
db.projects
db.experiments
db.samples
db.pools
db.users
db.index_kits
db.contacts
db.lanes
db.features
db.feature_kits
db.sequencers
db.adapters
db.plates
db.barcodes
db.lab_preps
db.kits
db.links
db.files
db.comments
db.seq_runs
db.events
db.groups
db.shares
```

#### Common Methods
- Get object:
    - `db.<submodule>.get(<obj-id>)  # returns None if not found`
    - `db.<submodule>[<obj-id>] # raises exception if not found`
- Query objects:
    - `db.<submodule>.find() # returns list of objects`
- Create object:
    - `db.<submodule>.create(<args>) # returns created object`
- Update object:
    - `db.<submodule>.update(<obj>) # returns updated object or None if not found`
- Delete object:
    - `db.<submodule>.delete(<obj-id>) # returns True if deleted, False if not found`

- Additionally, in following cases you can use special columns as keys:
```python
db.projects["<project identifier>"]
db.experiments["<experiment name>"]
db.users["user@email.com"]
```