FROM python:3.11.3-slim-buster

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt install build-essential -y
RUN apt install libpq-dev -y
RUN apt install curl -y

RUN pip install --upgrade pip
COPY limbless-app/limbless-db /usr/src/limbless-db
RUN pip install -r /usr/src/limbless-db/requirements.txt
RUN pip install /usr/src/limbless-db
COPY rf-scanner/runner.py /usr/src/app/