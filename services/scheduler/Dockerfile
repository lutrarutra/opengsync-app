FROM --platform=linux/x86_64 python:3.13-slim

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt update
RUN apt install cron build-essential wget libpq-dev curl -y

RUN pip install --upgrade pip

COPY opengsync-app/opengsync-db /usr/src/app/opengsync-db
RUN pip install /usr/src/app/opengsync-db
COPY ./scheduler /usr/src/app/scheduler
RUN pip install /usr/src/app/scheduler