import os
import pytz
import datetime as dt

PAGE_LIMIT = 15
TIMEZONE: pytz.BaseTzInfo = pytz.timezone(os.environ['TIMEZONE'])


def localize(timestamp: dt.datetime) -> dt.datetime:
    return pytz.utc.localize(timestamp).astimezone(TIMEZONE)

from . import categories  # noqa
from .core.DBHandler import DBHandler    # noqa
from .core.DBSession import DBSession    # noqa
from .core import exceptions    # noqa