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
1. `opengsync-app` - Flask web server
1. `opengsync-db` - PostgreSQL database
1. `celery-beat` - Periodic task scheduler
1. `celery-worker` - Asynchronous task worker to scan illumina run folder, update statuses, clean old files etc.
1. `nginx` - Reverse proxy for static files (only prod)
1. `pgadmin` - PostgreSQL admin interface @ `https://localhost:5050`
1. `tailwind-compiler` - Compiles tailwind css
1. `redis` - Redis server for celery broker and caching

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
1. `db` - Database files

# Production Server service

## Initial Setup

### 1. Create folders with correct permissions
- `cp templates/template.env .env`
    - Populate .env as required.
- `cp templates/opengsync.yaml .`
    - Populate opengsync.yaml as required.

```sh
# ${PUID} ${PGID} from .env
source .env
sudo mkdir -p db && sudo chown -R ${PUID}:${PGID} db && sudo chmod -R 750 db
sudo mkdir -p db/postgres && sudo chown -R ${PUID}:${PGID} db/postgres
sudo mkdir -p db/postgres && sudo chown -R ${PUID}:${PGID} db/archive && sudo chmod -R 750 db/archive

sudo mkdir -p ${MEDIA_DIR} && sudo chown -R ${PUID}:${PGID} ${MEDIA_DIR} && sudo chmod -R 700 ${MEDIA_DIR} 
sudo mkdir -p ${UPLOADS_DIR} && sudo chown -R ${PUID}:${PGID} ${UPLOADS_DIR} && sudo chmod -R 700 ${UPLOADS_DIR}
sudo mkdir -p ${LOG_DIR} && sudo chown -R ${PUID}:${PGID} ${LOG_DIR} && sudo chmod -R 700 ${LOG_DIR}

sudo mkdir -p ${LOG_DIR}/{celery-worker,celery-beat,backup,opengsync}
sudo chown -R ${PUID}:${PGID} ${LOG_DIR}/{celery-worker,celery-beat,backup,opengsync}
sudo chmod -R 700 ${LOG_DIR}/{celery-worker,celery-beat,backup,opengsync}

sudo chown root:root .env && sudo chmod 400 .env
```

### 2. Configure Shareable Directories
```sh
touch compose.override.yaml
```
#### Include the paths you want to share from, e.g.:
```yaml
services:
    opengsync-app:
        volumes:
            - /mnt/projects:/share/PROJECTS:ro
            - /mnt/raw_data:/share/RAW_DATA:ro
    nginx:
        volumes:
            - /mnt/projects:/share/PROJECTS:ro
            - /mnt/raw_data:/share/RAW_DATA:ro
```

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

### 4. Production Deploy
- `make deploy` - builds and starts the containers in detached mode.
- `make prod-logs` - streams logs from `opengsync-app` container.
- `make prod-logs-all` - streams logs from all containers.
- `make prod-stop` - stops the containers

### 5. Notes
- Services are defined with `restart: unless-stopped` policy, so they will automatically restart if the server reboots or if the container crashes as long as docker service is enabled and running (`systemctl status docker`, `systemctl enable docker`).

# Setup for Development (virtual/conda environment recommended)

* ✅ Hot reload python files on change.
* ✅ Compilation of scss files on change.

- using uv:
    - `uv sync`

- or using pip:
    ```bash
        pip install -e services/opengsync-app/opengsync-db
        pip install -e services/opengsync-app/opengsync-server
        pip install -e services/opengsync-app/opengsync-api
        mkdir -p db
        mkdir -p db/pgadmin && sudo chown -R 5050:5050 db/pgadmin
    ```

## Run Debug
- `make debug` - starts the app in debug mode with hot reload and streams logs from `opengsync-app` container.
- `make dev-stop` - stops the containers


# pgAdmin
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

# Tests
- SQL Database models, links
- Common library prep table requirements

# Share

## Download shared file:
- Rclone sync (WebDAV):
```sh
rclone sync \
    ":webdav,url='https://<url>/api/webdav/share/<token>':/" \
    <outdir> \
    --progress \
    --transfers=8 \
    --checkers=16 \
    --use-server-modtime \
    --verbose
```
- Rclone copy:
```sh
rclone copy --http-url https://<url>/files/share/rclone/<token> \
    :http: <outdir> -v --stats-log-level NOTICE \
    --stats 500ms --progress
```

- Wget:
```sh
wget -P <outdir> \
    --reject="index.html*" --recursive --level=99 --no-parent \
    --no-check-certificate -k -e robots=off -nH --cut-dirs=3 \
    https://<url>/files/share/rclone/<token>
```

# ORM Database
```python
db = DBHandler()
db.connect(
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host="< server ip >",
    port=os.environ["POSTGRES_PORT"],
    db=os.environ["POSTGRES_DB"],
)
```

- When reading/writing data from/to db, db session must be opened: `db.open_session()`
- If session is closed (and `auto_open=False`), querying the database will raise `sqlalchemy.orm.exc.DetachedInstanceError`.
- If `auto_open=True` when creating `DBHandler`-object, session is opened and closed automatically. But lazy loading of relationships will not work.
- `db.close_session()` writes/commits the updates to db and closes the session.

## DB API

Here is a comprehensive overview of how to interact with the database using the internal `opengsync_db` API. 

The API consists of three major components:
1.  **`SyncDBHandler`**: Manages the connection pool, engine, and threaded sessions.
2.  **`queries`**: Stores entity-specific builder functions that return pre-constructed `sqlalchemy.Select` statements or un-saved model instances.
3.  **`SyncSession`**: An extension of the standard SQLAlchemy `Session` class equipped with custom fetch, iteration, and pagination mechanisms to consume the statements built by `queries`.

---

### 1. Connection & Session Management (`SyncDBHandler`)

`SyncDBHandler` acts as a thread-safe factory wrapper around SQLAlchemy's Engine and `sessionmaker`. 

**Setup & Connection:**
```python
from opengsync_db.core.SyncDBHandler import SyncDBHandler

db_handler = SyncDBHandler(logger=my_logger, auto_commit=False, expire_on_commit=False)

# Establish connection via psycopg wrapper
db_handler.connect(
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host="localhost",
    port=5432
)
```

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
)
set_db(db)  # Important to activate the extension
```

Then you can run any query in a notebook cell without explicitly opening a session, e.g:
```python
project = db.session.get_or_fail(queries.project.select(project_id=1))
project.title = "New Title"
db.session.commit()  # need to manually commit changes to db if auto_commit=False (default)
```

**Lifecycle Methods:**
Sessions act as local transactions and should be explicitly opened and closed depending on context.

```python
# 1. Open a new session scope
session = db_handler.open_session(autoflush=True)

try:
    # ... use the session to modify/read data
    pass
    
    # 2. Close session successfully (commits if auto_commit is True, else pass commit=True)
    db_handler.close_session(commit=True)
except Exception:
    # 3. Rollback the active transaction
    db_handler.close_session(rollback=True)
```

*(Note: `db_handler` also exposes blueprints `db_handler.pd` and `db_handler.actions` for batch pandas jobs or multi-step tasks)*

---

### 2. Building Queries (`opengsync_db.queries`)

Rather than relying purely on direct ORM syntax throughout the application, the `queries` module unifies structure-specific logic. They **do not execute** the queries by themselves, but rather construct standard `sqlalchemy.Select` statements.

```python
from opengsync_db import queries as Q
from opengsync_db.categories import ProjectStatus

# Create uncommitted ORM model instances 
new_project = Q.project.create(
    title="Alpha Genome",
    description="Sample data set",
    owner_id=1,
    status=ProjectStatus.ACTIVE
)
# Add it to the session
db.session.save(new_project, flush=True)  # flush=True to get the id of the new project without committing
# commit session to write to db
db.session.commit()

# Builder functions (like `select()`) generate filtered SQLAlchemy statements
stmt = Q.project.select(
    owner_id=1,
    status=ProjectStatus.DRAFT,
    search_title="Alpha"
)

# The returned `stmt` can be further modified with custom filters, joins, order_by, etc. before execution.
stmt = stmt.order_by(Project.created_at.desc()).limit(10)
```

---

### 3. Executing & Retrieving Data (`SyncSession`)

Once you build your SQL statement through the `queries` utility, use `SyncSession`'s custom API to elegantly extract the data.

#### Fetching Single Objects
```python
# Returns the first object, or None if no match is found
project = session.first(stmt)

# Returns a single object, but raises ModelNotFoundException if none exist
project = session.get_or_fail(stmt)

# Shorthand alias to .get_or_fail() using subscripts
project = session[stmt]
```

#### Fetching Multiple Objects
```python
from sqlalchemy import desc
from opengsync_db.models import Project

# Returns a List of objects matching the criteria
projects = session.get_all(
    stmt, 
    limit=50, 
    order_by=desc(Project.id)
)

# Yields objects one by one (executes internally using `yield_per` chunking).
# Ideal for huge sets/export operations.
for project in session.iter(stmt, batch_size=200):
    print(project.title)
```

#### Pagination and Quantities
```python
# Evaluates exactly how many rows match the statement
total_items = session.count(stmt)

# Returns True if at least 1 row matches
is_existing = session.exists(stmt)

# Returns a Tuple: (List[Objects], TotalCount)
# Handled intelligently: automatically skirts queries where offset > total count
page_results, total_count = session.page(
    stmt, 
    page=0, 
    limit=10, 
    order_by=Project.id
)
```

#### Evaluating Scalars and Modifying State
```python
# Retrieve arbitrary SQL scalar values (useful when computing permissions/sums)
access_level = session.get_access_level(Q.project.access_level(user_id=10))

# Instantly adds and flushes (but doesn't commit) a model to the underlying active transaction
session.save(new_project, flush=True)

# Instantly deletes and flushes the object state
session.delete(existing_project, flush=True)
```

#### Pandas DataFrame
- User one of the pre-existing queries, e.g:
    - `db.pd.get_project_libraries(project_id)`
    - `db.pd.get_seq_requestor(seq_request_id)`
- Or custom query:

## Backup and Restore

### WAL Archiving
- Enabled by default in `templates/postgresql.conf`: `archive_command = 'cp %p /var/lib/postgresql/wal/%f'` (mounted on `${DB_DIR}/archive/wal`)

### Nightly Base Backups (and DB Dumps)
- Service: `backup-service` handles nightly base backups and dumps at 2:00 AM every day.
- Base backup stored in `${DB_DIR}/archive/base`
- DB dump stored in `${DB_DIR}/archive/dump`

### Restore from Base Backup + WAL
1. `tar -xzf <date>.tar.gz`
2. `cp backups/base/<date> db/postgres/`
5. `docker compose -f compose.yaml -p opengsync run --rm postgres` # should start the postgres successfully


# Customization
- Customization of the app can be done by modifying the `opengsync.yaml` configuration.
- Mail templates can be mounted to `/templates/custom/` for `opengsync-app`-container:
    - `email-signature.html` - Email signature template for all emails.
    - `share-internal-access.html` - Template for share access email sent to users with internal share access.
    - `share-project-data-email-footer.html` - Footer template for share project data email sent to clients.
    - `share-project-data-email-header.html` - Header template for share project data email sent to clients.