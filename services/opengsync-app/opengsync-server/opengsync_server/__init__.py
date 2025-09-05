import os

import pandas as pd
import yaml
import pytz
import redis
from flask_htmx import HTMX
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_caching import Cache
from itsdangerous import URLSafeTimedSerializer

from loguru import logger

from opengsync_db import DBHandler

from .core.LogBuffer import log_buffer
from .tools import RedisMSFFileCache
from .core.FlashCache import FlashCache
from .core.FileHandler import FileHandler
from .tools import MailHandler

logger.remove()
logger.add(log_buffer.write, format="{message}", serialize=True, catch=True)

# Show all columns without truncation
pd.set_option('display.max_columns', None)
# Show all rows without truncation
pd.set_option('display.max_rows', None)
# Disable column width truncation (so wide columns show fully)
pd.set_option('display.max_colwidth', None)
# Optional: increase the display width of your console (characters per line)
pd.set_option('display.width', 1000)

DEBUG = os.getenv("OPENGSYNC_DEBUG", "0") == "1"
SECRET_KEY = os.environ["SECRET_KEY"]
TIMEZONE = pytz.timezone(os.environ["TIMEZONE"])

htmx = HTMX()
bcrypt = Bcrypt()
login_manager = LoginManager()
serializer = URLSafeTimedSerializer(SECRET_KEY)
mail_handler = MailHandler()

db = DBHandler(logger=logger, expire_on_commit=True, auto_open=False)
route_cache = Cache()
msf_cache = RedisMSFFileCache()
session_cache = redis.Redis(host="redis-cache", port=int(os.environ["REDIS_PORT"]), db=3)
flash_cache = FlashCache()
file_handler = FileHandler()