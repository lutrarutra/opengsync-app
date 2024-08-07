import os
from functools import wraps
import pytz
import datetime as dt

PAGE_LIMIT = 15
if (__timezone := os.environ.get("TIMEZONE")) is None:
    import tzlocal
    __timezone = tzlocal.get_localzone_name()
TIMEZONE: pytz.BaseTzInfo = pytz.timezone(__timezone)


def localize(timestamp: dt.datetime) -> dt.datetime:
    return pytz.utc.localize(timestamp).astimezone(TIMEZONE)


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