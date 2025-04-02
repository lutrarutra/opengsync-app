FROM python:3.11-bookworm

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt install build-essential -y
RUN apt install libpq-dev -y
RUN apt install curl -y
RUN apt install postgresql-client -y
RUN pip install --upgrade pip
COPY . /usr/src/app/
RUN pip install /usr/src/app/limbless-db
RUN pip install /usr/src/app/limbless-server