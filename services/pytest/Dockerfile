FROM python:3.13-bookworm

# set work directory
WORKDIR /usr/src/app

# install dependencies
RUN apt update
RUN apt install build-essential libpq-dev curl postgresql-client -y

RUN pip install --upgrade pip
COPY ./opengsync-app/opengsync-db /usr/src/app/opengsync-db
RUN pip install /usr/src/app/opengsync-db
COPY ./pytest/requirements.txt /usr/src/app/
RUN pip install -r requirements.txt