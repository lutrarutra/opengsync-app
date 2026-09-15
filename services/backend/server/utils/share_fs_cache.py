import hashlib
import json
from typing import Any

from loguru import logger
from redis.exceptions import RedisError

from ..core import config
from ..core.redis import RedisClient


SHARE_TOKEN_TTL = 300
LISTING_TTL = 60
PROPFIND_TTL = 300
WALK_TTL = 60


def _cache_key(token: str, kind: str, **params: Any) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"share-fs:{token}:{kind}:{digest}"


def _get(redis: RedisClient | None, key: str) -> Any | None:
    if redis is None or config.settings.ENVIRONMENT != "prod":
        return None

    try:
        value = redis.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            return None
        return json.loads(value)
    except (RedisError, TypeError, ValueError, UnicodeError):
        logger.exception("Failed to read share filesystem cache key {}", key)
        return None


def _set(redis: RedisClient | None, key: str, value: Any, ttl: int) -> None:
    if redis is None or config.settings.ENVIRONMENT != "prod":
        return

    try:
        redis.set(key, json.dumps(value), ex=ttl)
    except (RedisError, TypeError, ValueError):
        logger.exception("Failed to write share filesystem cache key {}", key)


def get_listing(
    redis: RedisClient | None,
    token: str,
    *,
    subpath: str,
    limit: int | None,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> list[dict[str, Any]] | None:
    key = _cache_key(
        token,
        "list",
        subpath=subpath,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return _get(redis, key)


def set_listing(
    redis: RedisClient | None,
    token: str,
    value: list[dict[str, Any]],
    *,
    subpath: str,
    limit: int | None,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> None:
    key = _cache_key(
        token,
        "list",
        subpath=subpath,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    _set(redis, key, value, LISTING_TTL)


def get_propfind(
    redis: RedisClient | None,
    token: str,
    *,
    subpath: str,
    depth: int,
) -> list[dict[str, Any]] | None:
    return _get(redis, _cache_key(token, "propfind", subpath=subpath, depth=depth))


def set_propfind(
    redis: RedisClient | None,
    token: str,
    value: list[dict[str, Any]],
    *,
    subpath: str,
    depth: int,
) -> None:
    _set(redis, _cache_key(token, "propfind", subpath=subpath, depth=depth), value, PROPFIND_TTL)


def get_walk(redis: RedisClient | None, token: str, *, subpath: str) -> list[dict[str, Any]] | None:
    return _get(redis, _cache_key(token, "walk", subpath=subpath))


def set_walk(
    redis: RedisClient | None,
    token: str,
    value: list[dict[str, Any]],
    *,
    subpath: str,
) -> None:
    _set(redis, _cache_key(token, "walk", subpath=subpath), value, WALK_TTL)


def claim_share_audit(redis: RedisClient | None, key: str, ttl: int) -> bool:
    """Return True if this caller should write the share-access audit log."""
    if redis is None:
        return True
    try:
        return bool(redis.set(key, "1", nx=True, ex=max(60, ttl)))
    except (RedisError, TypeError, ValueError):
        logger.exception("Failed to claim share audit key {}", key)
        return True


def invalidate(redis: RedisClient | None, token: str) -> None:
    if redis is None:
        return

    try:
        redis.delete(f"share-token:{token}")
        redis.delete_pattern(f"share-fs:{token}:*")
        redis.delete_pattern(f"share-audit:{token}:*")
    except (RedisError, TypeError, ValueError):
        logger.exception("Failed to invalidate share cache for token {}", token)
