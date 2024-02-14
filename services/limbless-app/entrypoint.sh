#!/bin/sh

if [ $LIMBLESS_DEBUG -eq 1 ] && [$LIMBLESS_TESTING -ne 1]; then
    python3 init_db.py --create_users --add_indices
fi

if [ $? -eq 0 ]; then
    exec "$@"
else
    exit 1
fi