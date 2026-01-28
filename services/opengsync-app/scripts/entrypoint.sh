#!/bin/bash
set -e  # Exit immediately if a command fails

# uv run opengsync-init-db
python /app/scripts/cli_init.py

# Use 'exec' so Python becomes PID 1 
exec python /app/scripts/debug.py --host=0.0.0.0 --port=${OPENGSYNC_PORT}