#!/bin/sh

if [ $LIMBLESS_DEBUG -eq 0 ]; then
    python3 prod_init.py
fi

python3 init_db.py --create_users --add_indices

if [ $? -eq 0 ]; then
    echo "Database initialized successfully"
    exec "$@"
else
    echo "Database initialization failed"
    exit 1
fi