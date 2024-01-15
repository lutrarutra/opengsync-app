# pull official base image
FROM python:3.11.3-slim-buster

# set work directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install dependencies
RUN apt update
RUN apt install build-essential -y
RUN apt install libpq-dev -y
RUN apt install wget -y
RUN apt install unzip -y
RUN pip install --upgrade pip
RUN pip install gunicorn
COPY ./requirements.txt /usr/src/app/requirements.txt
RUN pip install -r requirements.txt

# copy project
COPY . /usr/src/app/

EXPOSE 5000