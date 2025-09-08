FROM python:3.13-slim

ARG APPUSER=0
ARG APPGROUP=0

RUN [ "${APPGROUP}" -eq 0 ] || groupadd -g ${APPGROUP} opengsync
RUN [ "${APPUSER}" -eq 0 ] || useradd -u ${APPUSER} -g ${APPGROUP} -s /bin/bash opengsync

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt install build-essential libpq-dev curl postgresql-client -y

RUN pip install --upgrade pip

COPY . /usr/src/app/
RUN pip install /usr/src/app/opengsync-db
RUN pip install /usr/src/app/opengsync-server