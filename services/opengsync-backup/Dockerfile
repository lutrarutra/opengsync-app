# --- BACKUP ---
FROM postgres:17-alpine as backup
RUN apk update && \
    apk add --no-cache \
    cronie \
    bash \
    && rm -rf /var/cache/apk/*

RUN mkdir -p /backups/dump /backups/base

COPY backup.sh /backup.sh
COPY entrypoint.sh /entrypoint.sh

RUN mkdir -p /var/log

RUN echo "0 2 * * * /backup.sh >> /var/log/backup.log 2>&1" > /etc/crontabs/root

RUN chmod +x /backup.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]