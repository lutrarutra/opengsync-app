#!/bin/sh
# Runs as root from /docker-entrypoint.d/ before nginx starts. Puts the nginx user into a
# group with GID $MEDIA_GID so workers can read the media directory bind-mounted from the
# host (written by the app as PUID:PGID, not world-readable).
set -eu

if getent group mediagroup >/dev/null; then
    groupmod -o -g "$MEDIA_GID" mediagroup
else
    groupadd -o -g "$MEDIA_GID" mediagroup
fi
usermod -aG mediagroup nginx
