#!/bin/bash

opengsync-init-db


if [ $? -eq 0 ]; then
    python3 /app/debug.py --host=0.0.0.0 --port=${OPENGSYNC_PORT}
else
    exit 1
fi