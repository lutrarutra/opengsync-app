FROM python:3.13-slim

# set work directory
WORKDIR /app

# install dependencies
RUN apt update
RUN apt install build-essential libpq-dev curl postgresql-client -y

RUN pip install --upgrade pip
COPY ./opengsync-app/opengsync-db /app/opengsync-db
RUN pip install /app/opengsync-db
COPY ./pytest/requirements.txt /app/
RUN pip install -r requirements.txt