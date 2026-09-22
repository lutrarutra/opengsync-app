#!/bin/sh
set -e

if [ "$#" -eq 0 ] || [ "$1" = "api" ]; then
  PORT="${PORT:-5000}"
  WORKERS="${GUNICORN_WORKERS:-4}"
  exec gunicorn server.main:app \
    --workers "$WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT}" \
    --forwarded-allow-ips='*'
fi

exec "$@"