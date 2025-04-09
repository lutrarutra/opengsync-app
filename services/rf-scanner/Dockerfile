FROM --platform=linux/x86_64 python:3.13-slim

# set work directory
WORKDIR /usr/src/app
ARG RUN_FOLDER_SCAN_INTERVAL_MINS

# install dependencies
RUN apt update
RUN apt update
RUN apt install cron build-essential wget libpq-dev curl -y

RUN pip install --upgrade pip

COPY limbless-app/limbless-db /usr/src/app/limbless-db
RUN pip install /usr/src/app/limbless-db
COPY ./rf-scanner /usr/src/app/rf-scanner
RUN pip install /usr/src/app/rf-scanner

RUN chmod +x /usr/src/app/rf-scanner/entrypoint.sh
RUN chmod +x /usr/src/app/rf-scanner/run.sh

RUN rm -f /var/log/cron.log
RUN touch /var/log/cron.log
RUN echo "*/${RUN_FOLDER_SCAN_INTERVAL_MINS} * * * * /usr/src/app/rf-scanner/run.sh >> /var/log/cron.log 2>&1" > /etc/cron.d/mycron
RUN chmod 0644 /etc/cron.d/mycron
RUN crontab /etc/cron.d/mycron