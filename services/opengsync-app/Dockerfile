FROM python:3.13-slim

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt install build-essential libpq-dev curl postgresql-client -y

RUN pip install --upgrade pip

COPY . /usr/src/app/
RUN pip install /usr/src/app/opengsync-db
RUN pip install /usr/src/app/opengsync-server