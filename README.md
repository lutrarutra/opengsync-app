# limbless
Web app for NGS sample/library/project tracking

## Installation
    - `pip install -r requirements.txt`
    - `mkdir -p data && cd data`
    - `wget https://github.com/twbs/bootstrap/archive/v5.3.2.zip`
    - `unzip v5.3.2.zip`
    - `rm v5.3.2.zip`
    - `mkdir -p ../limbless/static/style/bootstrap`
    - `mv bootstrap-5.3.2/scss ../limbless/static/style/bootstrap`

## Run flask debug server
    - `docker compose up`
    - `flask run`

## pgAdmin Interface
    - `http://localhost:5050`
    - username: `$(PGADMIN_EMAIL)`
    - password: `$(PGADMIN_PASSWORD)`

## pgAdmin Server Setup
    - host: `host.docker.internal`
    - port: `5432`
    - username: `$(POSTGRES_USER)`
    - password: `$(POSTGRES_PASSWORD)`

If host `host.docker.internal` does not work, try `docker inspect limbless_postgres_1 | grep IPAddress` and use the IP address of the container:
    - `docker ps`
    - `docker inspect <container_id> | grep IPAddress`