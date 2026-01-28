FROM python:3.13-slim

WORKDIR /app

RUN apt update
RUN apt install cron build-essential wget libpq-dev curl -y

RUN pip install --upgrade pip

COPY opengsync-app/opengsync-db /app/opengsync-db
RUN pip install /app/opengsync-db
COPY celery/scheduler /app/scheduler
RUN pip install /app/scheduler