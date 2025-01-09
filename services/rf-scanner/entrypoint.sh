#!/bin/sh

mkdir -p /illumina_run_folder

if [ -f /var/log/cron.log ]; then
    cat /var/log/cron.log >> /var/log/history.log
    rm -f /var/log/cron.log
fi
touch /var/log/cron.log 

printenv | grep -v "no_proxy" >> /etc/environment

echo "Starting scanning: ${ILLUMINA_RUN_FOLDER}"
cron
tail -f /var/log/cron.log

