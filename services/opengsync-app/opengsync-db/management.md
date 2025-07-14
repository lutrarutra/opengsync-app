# Base backup

```sh
# in host
docker exec -it postgres sh
# In postgres container
pg_basebackup \
  -U bsf \
  -D /var/lib/postgresql/base \
  -F tar \
  -X fetch \
  -P
```

# DB Dump
```sh
pg_dump -U admin -d limbless -F c -f limbless.dump
```
## Run docker container
```sh
docker run -d \
    --name pgrestore \
    -e POSTGRES_USER=admin \
    -e POSTGRES_PASSWORD=password \
    -e POSTGRES_DB=limbless \
    -v '/Users/agynter/Downloads/limbless.dump':/limbless.dump \
    -p 5432:5432 \
    postgres:16rc1-alpine3.17
```

```sh
docker exec -it postgres sh
```

```sh
# --data-only restores only the data, i.e. not the schema
pg_restore --data-only -U bsf -d opengsync limbless.dump
```