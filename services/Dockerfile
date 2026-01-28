# --- BASE: Common system deps and uv setup ---
FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN chmod 777 /app

# --- BUILDER: Install dependencies ONLY ---
FROM base AS builder
COPY pyproject.toml uv.lock ./
COPY packages/opengsync-db/pyproject.toml ./packages/opengsync-db/
COPY packages/opengsync-server/pyproject.toml ./packages/opengsync-server/
COPY packages/opengsync-worker/pyproject.toml ./packages/opengsync-worker/
RUN uv sync --frozen --no-install-project

# --- SERVER ---
FROM builder AS opengsync-app
RUN apt update && apt install build-essential libpq-dev curl postgresql-client -y

COPY packages /app/packages
COPY ./services/opengsync-app/scripts /app/scripts
RUN uv sync --frozen


# --- CELERY BASE ---
FROM builder AS celery-base
RUN apt-get update && apt-get install -y cron wget && rm -rf /var/lib/apt/lists/*
RUN uv pip install celery[redis]

# --- CELERY WORKER ---
FROM celery-base AS celery-worker
COPY packages /app/packages
RUN uv sync --frozen