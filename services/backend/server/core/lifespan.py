import sys
import os
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from redis import ConnectionPool

from opengsync_db import SyncDBHandler

from . import config, mailer, secrets, templates

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

    if os.path.exists(config_path := "/app/opengsync.yaml"):
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)
        app_config = config.AppConfig.model_validate(raw)
        config.settings.inject_app_config(app_config)
        templates.j2.env.globals["sample_submission_windows"] = config.settings.app_config.sample_submission_windows
        logger.info("AppConfig injected from opengsync.yaml")
    else:
        logger.warning("opengsync.yaml not found, app_config unavailable")

    os.makedirs(config.settings.app_config.log_folder, exist_ok=True)
    logger.add(
        f"{config.settings.app_config.log_folder}/{{time:YYYY-MM-DD}}.log",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        filter=lambda record: not record["extra"].get("audit"),
        level="DEBUG" if config.settings.ENVIRONMENT != "prod" else "INFO"
    )
    os.makedirs(f"{config.settings.app_config.log_folder}/audits", exist_ok=True)
    logger.add(
        f"{config.settings.app_config.log_folder}/audits/{{time:YYYY-MM-DD}}.jsonl",
        rotation="1 day",
        compression="zip",
        serialize=True,
        filter=lambda record: record["extra"].get("audit") is True,
        level="INFO",
    )

    app.state.db_handler = SyncDBHandler(default_row_limit=None)
    app.state.db_handler.connect(
        user=config.settings.POSTGRES_USER,
        password=config.settings.POSTGRES_PASSWORD,
        host=config.settings.POSTGRES_HOST,
        db=config.settings.POSTGRES_DB,
        port=config.settings.POSTGRES_PORT
    )
    logger.info("Connected to the database")

    if app.state.db_handler._engine is None:
        raise Exception("DB connection could not be established")
    
    app.state.mailer = mailer.Mailer()
    app.state.redis_pool = ConnectionPool.from_url(config.settings.REDIS_URL)
    app.state.bcrypt = secrets.BcryptCompat()

    from .templates import j2
    from .config import settings
    j2.env.globals["contact_email"] = settings.app_config.personalization.email
    j2.env.globals["organization_name"] = settings.app_config.personalization.organization

    # FastAPICache.init(RedisBackend(Redis(connection_pool=app.state.redis_pool)), prefix="fastapi-cache")
    yield

    app.state.db_handler.close()
    if app.state.db_handler._engine:
        app.state.db_handler._engine.dispose()

    app.state.redis_pool.disconnect()