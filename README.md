# limbless
Web app for NGS sample/library/project tracking

## Installation for development
    - `pip install -r services/limbless-app/limbless-server/requirements.txt`
    - `pip install -e services/limbless-app/limbless-server`
    - `pip install -r services/limbless-app/limbless-db/requirements.txt`
    - `pip install -e services/limbless-app/limbless-db`

## Run with flask debug server
    - `chmod +x debug.sh`
    - `./debug.sh`
## Unit tests
    - `chmod +x test.sh`
    - `./test.sh`
## Production
    - `chmod +x prod.sh`
    - `./prod.sh`

## pgAdmin Interface
    - `http://localhost:5050`
    - username: `$(PGADMIN_EMAIL)`
    - password: `$(PGADMIN_PASSWORD)`

## pgAdmin Server Setup
    - Dev dir: `db/dev_pgadmin` permissions should be 5050:5050 (`sudo chown -R 5050:5050 db/dev_pgadmin`)
    - Prod dir: `db/pgadmin` permsissions should be 5050:5050 (`sudo chown -R 5050:5050 db/pgadmin`)
    - host: `postgres` & port: `5432` or
    - Find the IP address of the container:
        1. `docker ps`
        2. `docker inspect limbless-postgres-db | grep IPAddress`
    - username: `$(POSTGRES_USER)`
    - password: `$(POSTGRES_PASSWORD)`