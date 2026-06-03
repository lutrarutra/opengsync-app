import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from redis.asyncio import ConnectionPool, Redis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from opengsync_db import AsyncDBHandler

from . import config, mailer


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

    app.state.db_handler = AsyncDBHandler()
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

    FastAPICache.init(RedisBackend(Redis(connection_pool=app.state.redis_pool)), prefix="fastapi-cache")
    yield

    await app.state.db_handler.close()
    if app.state.db_handler._engine:
        await app.state.db_handler._engine.dispose()

    await app.state.redis_pool.disconnect()