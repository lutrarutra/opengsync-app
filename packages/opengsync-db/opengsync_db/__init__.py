import os
from functools import wraps
import datetime as dt
from typing import Callable
from zoneinfo import ZoneInfo
from sqlalchemy import exc

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("opengsync-db")
except PackageNotFoundError:
    __version__ = "0.0.0"

PAGE_LIMIT = 15


def resolve_timezone_name() -> str:
    """The display timezone: the TZ env var, else the host's zone, else UTC.
    An empty TZ (e.g. an unset ${TIMEZONE} in compose) counts as unset."""
    if name := os.environ.get("TZ", "").strip().lstrip(":"):
        return name
    import tzlocal
    return tzlocal.get_localzone_name() or "UTC"


# The single source of truth for the app's timezone; the server's settings.TIMEZONE returns this.
# Timestamps are stored in UTC and converted to this zone for display and for naive user input.
TIMEZONE_NAME: str = resolve_timezone_name()
TIMEZONE: ZoneInfo = ZoneInfo(TIMEZONE_NAME)


def localize(timestamp: dt.datetime, timezone: dt.tzinfo | str | None = None) -> dt.datetime:
    """Convert a stored timestamp to local time (``TIMEZONE`` unless given). Naive values are taken as UTC."""
    if timezone is None:
        timezone = TIMEZONE
    elif isinstance(timezone, str):
        timezone = ZoneInfo(timezone)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    return timestamp.astimezone(timezone)


def to_utc(timestamp: dt.datetime) -> dt.datetime:
    """Convert to UTC for storage. Naive values are taken as local time in ``TIMEZONE`` (e.g. picker input)."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=TIMEZONE)
    return timestamp.astimezone(dt.timezone.utc)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


from . import categories  # noqa
from .core.SyncSession import SyncSession  # noqa
from .core.SyncDBHandler import SyncDBHandler  # noqa
from .core.AsyncSession import AsyncSession  # noqa
from .core.AsyncDBHandler import AsyncDBHandler  # noqa
from .core import exceptions  # noqa
from .core import units  # noqa
from .core import utils  # noqa
from .core import actions  # noqa


def db_session(db: SyncDBHandler):
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                db.open_session()
                res = f(*args, **kwargs)
                db.close_session()
                return res
            except exc.PendingRollbackError as e:
                db.error(e)
                db.close_session(commit=False, rollback=True)
                raise exceptions.RollBackTriggered("Database session failed due to pending rollback. Please try again.") from e
            except exc.IntegrityError as e:
                db.error(e)
                db.close_session(commit=False, rollback=True)
                raise exceptions.RollBackTriggered("Database integrity error occurred. Please check your data.") from e
        return wrapper
    return decorator


__all__ = [
    "SyncDBHandler", "SyncSession",
    "AsyncDBHandler", "AsyncSession",
    "categories", "units",
    "exceptions", "utils",
    "actions"
]
