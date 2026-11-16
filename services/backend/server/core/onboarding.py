"""Customer onboarding tour progress (static/js/onboarding-tour.js), kept in Redis.

One JSON value per user under ``onboarding:{user_id}``, stored without a TTL so ``volatile-lru``
never evicts it. The prefix stays clear of ``user:*`` and ``*:user:{id}``, which the access cache
and user merges delete by pattern. Losing the value is harmless: the dashboard button offers the
tour again. Redis errors are logged and swallowed so registration and page loads never fail on them.
"""
import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from loguru import logger

from . import redis as rds


class Status(StrEnum):
    NEW = "NEW"                  # account just created/activated: auto-start on the next dashboard visit
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    SKIPPED = "SKIPPED"
    COMPLETED = "COMPLETED"


STEP_PATTERN = r"^[a-z0-9_.]{1,64}$"


class State(BaseModel):
    status: Status
    step: str | None = Field(default=None, pattern=STEP_PATTERN)
    # The request created during the tour; the request steps resume on its page.
    seq_request_id: int | None = None
    updated: dt.datetime | None = None


def _key(user_id: int) -> str:
    return f"onboarding:{user_id}"


def get_state(r: rds.RedisClient, user_id: int) -> State | None:
    try:
        data = r.get(_key(user_id))
    except RedisError:
        logger.exception(f"Failed to read onboarding state of user {user_id}")
        return None
    if data is None:
        return None
    try:
        return State.model_validate_json(data)  # type: ignore[arg-type]
    except ValueError:
        logger.warning(f"Discarding invalid onboarding state of user {user_id}")
        return None


def save_state(r: rds.RedisClient, user_id: int, state: State) -> None:
    state.updated = dt.datetime.now(dt.timezone.utc)
    try:
        r.set(_key(user_id), state.model_dump_json())
    except RedisError:
        logger.exception(f"Failed to save onboarding state of user {user_id}")


def mark_new(r: rds.RedisClient, user_id: int) -> None:
    """Auto-start the tour on the user's next dashboard visit."""
    save_state(r, user_id, State(status=Status.NEW))
