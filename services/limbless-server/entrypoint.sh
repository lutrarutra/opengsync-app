#!/bin/sh

python3 init_db.py --create_users --add_indices
exec "$@"