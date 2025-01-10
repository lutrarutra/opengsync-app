FROM --platform=linux/x86_64 python:3.12

# set work directory
WORKDIR /usr/src/app
ARG RUN_FOLDER_SCAN_INTERVAL_MINS

# install dependencies
RUN apt update
RUN apt update
RUN apt install cron -y
RUN apt install wget -y

RUN apt install build-essential -y
RUN apt install libpq-dev -y
RUN apt install curl -y

RUN pip install --upgrade pip
COPY limbless-app/limbless-db /usr/src/limbless-db
RUN pip install -r /usr/src/limbless-db/requirements.txt
RUN pip install /usr/src/limbless-db
RUN pip install Werkzeug==3.0.3
RUN pip install interop
COPY rf-scanner/entrypoint.sh /usr/src/app/entrypoint.sh
COPY rf-scanner/run.sh /usr/src/app/run.sh
RUN chmod +x /usr/src/app/entrypoint.sh
RUN chmod +x /usr/src/app/run.sh
RUN rm -f /var/log/cron.log
RUN touch /var/log/cron.log
RUN echo "*/${RUN_FOLDER_SCAN_INTERVAL_MINS} * * * * /usr/src/app/run.sh >> /var/log/cron.log 2>&1" > /etc/cron.d/mycron
RUN chmod 0644 /etc/cron.d/mycron
RUN crontab /etc/cron.d/mycron

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]