#!/bin/sh

if [ $LIMBLESS_DEBUG -eq 1 ]; then
    python3 init_db.py --create_users --add_indices
fi

if [ $? -eq 0 ]; then
    echo "Database initialized successfully"
    exec "$@"
else
    echo "Database initialization failed"
    exit 1
fi