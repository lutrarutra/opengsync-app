import os
from functools import wraps
import pytz
import datetime as dt
from typing import Callable

from sqlalchemy import exc

PAGE_LIMIT = 15
if (__timezone := os.environ.get("TIMEZONE")) is None:
    import tzlocal
    __timezone = tzlocal.get_localzone_name()
TIMEZONE: pytz.BaseTzInfo = pytz.timezone(__timezone)


def localize(timestamp: dt.datetime, timezone: pytz.BaseTzInfo | str = TIMEZONE) -> dt.datetime:
    """
    Args:
        timestamp (dt.datetime): if tzinfo is None, it's assumed to be utc
        timezone (pytz.BaseTzInfo | str, optional): Timezone to convert to. Defaults to 'tzlocal.get_localzone_name()'.

    Returns:
        dt.datetime: datetime object in the specified timezone
    """
    if isinstance(timezone, str):
        timezone = pytz.timezone(timezone)
    
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=pytz.utc)
    return timestamp.astimezone(timezone)


def to_utc(timestamp: dt.datetime) -> dt.datetime:
    return TIMEZONE.localize(timestamp).astimezone(pytz.utc)

from . import categories  # noqa
from .core.DBHandler import DBHandler    # noqa
from .core.DBSession import DBSession    # noqa
from .core import exceptions    # noqa


def db_session(db: DBHandler):
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

from .core import units  # noqa