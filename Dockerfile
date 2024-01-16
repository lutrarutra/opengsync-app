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
RUN apt install curl -y
RUN pip install --upgrade pip
COPY . /usr/src/app/
RUN mkdir uploads && touch uploads/hello
RUN pip install -r requirements.txt
RUN chmod +x entrypoint.sh

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]