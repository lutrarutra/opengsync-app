from typing import Any

from fastapi import Request, Response
from fastapi_cache.decorator import cache as decorator
from redis import ConnectionPool, Redis
from loguru import logger

__all__ = ["decorator"]

def request_key_builder(
    func,
    namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
):
    if request is None:
        raise NotImplementedError("Caching is only implemented for Fastapi route requests")
    
    key = f"{namespace}:{request.method}:{request.url.path}"

    if request.path_params:
        for name, value in request.path_params.items():
            key += f":{name}:{value}"

    if request.query_params:
        key += f":query:{request.query_params}"
    
    user = kwargs.get("user")
    if user and hasattr(user, "id"):
        key += f":user:{user.id}"
        
    return key

def scan_and_delete(pattern: str, redis_pool: ConnectionPool):
    cursor = 0

    try:
        with Redis(connection_pool=redis_pool) as redis:
            while True:
                cursor, keys = redis.scan(cursor, match=pattern, count=100)
                if keys:
                    redis.delete(*keys)
                if cursor == 0:
                    break
    except Exception as e:
        logger.exception(f"Error during cache invalidation: {e}")
