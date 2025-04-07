import os
from functools import wraps
import pytz
import datetime as dt

PAGE_LIMIT = 15
if (__timezone := os.environ.get("TIMEZONE")) is None:
    import tzlocal
    __timezone = tzlocal.get_localzone_name()
TIMEZONE: pytz.BaseTzInfo = pytz.timezone(__timezone)

LAB_PROTOCOL_START_NUMBER = int(os.environ["LAB_PROTOCOL_START_NUMBER"])


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
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with DBSession(db) as _:
                return func(*args, **kwargs)
        return wrapper
    return decorator