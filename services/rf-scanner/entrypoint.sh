#!/bin/sh

mkdir -p /illumina_run_folder

echo "Mounting: ${ILLUMINA_RUN_FOLDER} to /illumina_run_folder"

rclone mount cemm_cluster:${ILLUMINA_RUN_FOLDER} /illumina_run_folder --dir-cache-time 5s \
    --poll-interval 10s --vfs-cache-mode full --read-only --cache-dir=/data/cache/0 --allow-non-empty --allow-other --daemon

if [ -f /var/log/cron.log ]; then
    cat /var/log/cron.log >> /var/log/history.log
    rm -f /var/log/cron.log
fi
touch /var/log/cron.log 

printenv | grep -v "no_proxy" >> /etc/environment

echo "Starting scanning: ${ILLUMINA_RUN_FOLDER}"
cron
tail -f /var/log/cron.log

