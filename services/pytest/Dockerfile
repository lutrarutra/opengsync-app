FROM python:3.11.3-slim-buster

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt install build-essential -y
RUN apt install libpq-dev -y
RUN apt install curl -y
RUN apt install postgresql-client -y
RUN pip install --upgrade pip
COPY ./pytest/requirements.txt /usr/src/app/
COPY ./limbless-app/limbless-db /usr/src/app/limbless-db
RUN pip install -r requirements.txt
RUN pip install -r limbless-db/requirements.txt
RUN pip install ./limbless-db