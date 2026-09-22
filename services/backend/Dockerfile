# --- BASE: Common system deps and uv setup ---
FROM python:3.14-slim AS base
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
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=$VERSION
COPY pyproject.toml uv.lock ./
COPY packages/opengsync-db/pyproject.toml ./packages/opengsync-db/
COPY packages/opengsync-api/pyproject.toml ./packages/opengsync-api/
COPY packages/opengsync-worker/pyproject.toml ./packages/opengsync-worker/
COPY services/backend/pyproject.toml ./services/backend/
RUN uv sync --frozen --no-install-project --no-dev

# --- ALEMBIC MIGRATOR ---
FROM builder AS migrator
COPY packages/opengsync-db /app/packages/opengsync-db
COPY services/db/alembic /app/alembic
RUN uv sync --frozen --no-editable --no-dev
RUN uv pip install alembic

CMD alembic --config /app/alembic/alembic.ini upgrade head

# --- SERVER ---
FROM builder AS opengsync-app

COPY packages /app/packages
COPY services/backend /app/services/backend

ENV PYTHONPATH=/app/services/backend

RUN uv sync --frozen --no-editable --no-dev

COPY services/backend/templates /templates
COPY services/backend/static/js /static/js
COPY services/backend/static/images /static/images
COPY services/backend/static/resources /static/resources
COPY services/backend/static/style/email.css /static/style/email.css
COPY services/backend/scripts /app/scripts

CMD ["/app/scripts/entrypoint.sh", "api"]

# --- CELERY BASE ---
FROM builder AS celery-base
# RUN apt-get update && apt-get install -y cron wget && rm -rf /var/lib/apt/lists/*
RUN uv pip install celery[redis]

# --- CELERY WORKER ---
FROM celery-base AS celery-worker
COPY packages /app/packages
RUN uv sync --frozen --no-editable --no-dev

CMD celery -A opengsync_worker.celery worker --loglevel=info

# --- PYTEST ---
FROM builder AS pytest
ENV PYTHONPATH=/app/services/backend
COPY packages /app/packages
COPY services/backend /app/services/backend
COPY services/backend/static/resources/templates/library_prep/ /app/prep_tables
COPY services/backend/templates /templates
COPY services/backend/static /static
RUN mkdir -p /logs /static /templates
RUN uv sync --frozen --no-editable --no-dev
RUN uv pip install pytest httpx
# Copy tests last so edits only invalidate this layer (not uv sync).
COPY services/pytest/tests /app/tests
CMD ["pytest"]