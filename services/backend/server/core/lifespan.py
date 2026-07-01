import sys
import os
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from redis.asyncio import ConnectionPool, Redis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from opengsync_db import AsyncDBHandler

from . import config, mailer, secrets, templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.remove()
    logger.add(
        sys.stdout, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )
    logger.add(
        "/logs/{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG" if config.settings.ENVIRONMENT != "prod" else "INFO"
    )

    if os.path.exists(config_path := "/app/opengsync.yaml"):
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f)
        app_config = config.AppConfig.model_validate(raw)
        config.settings.inject_app_config(app_config)
        templates.j2.env.globals["sample_submission_windows"] = config.settings.app_config.sample_submission_windows
        logger.info("AppConfig injected from opengsync.yaml")
    else:
        logger.warning("opengsync.yaml not found, app_config unavailable")

    app.state.db_handler = AsyncDBHandler(default_row_limit=None)
    await app.state.db_handler.connect(
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

    from .msf_cache import msf_cache
    msf_cache.set_pool(app.state.redis_pool)
    logger.info("MSF cache connected to Redis")

    from .templates import j2
    from .config import settings
    j2.env.globals["contact_email"] = settings.app_config.personalization.email
    j2.env.globals["organization_name"] = settings.app_config.personalization.organization

    FastAPICache.init(RedisBackend(Redis(connection_pool=app.state.redis_pool)), prefix="fastapi-cache")
    yield

    await app.state.db_handler.close()
    if app.state.db_handler._engine:
        await app.state.db_handler._engine.dispose()

    await app.state.redis_pool.disconnect()