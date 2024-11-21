import sys
import os
import uuid

from loguru import logger
import pytz
from flask_htmx import HTMX
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_caching import Cache
from itsdangerous import URLSafeTimedSerializer

from limbless_db import DBHandler

from .tools import RedisMSFFileCache

logger.remove()

fmt = """{level} @ {time:YYYY-MM-DD HH:mm:ss} ({file}:{line} in {function}):
>   {message}"""


if os.getenv("LIMBLESS_DEBUG") == "1":
    logger.add(
        sys.stdout, colorize=True,
        format=fmt, level="DEBUG"
    )
else:
    date = "{time:YYYY-MM-DD}"
    logger.add(
        sys.stdout, colorize=True,
        format=fmt, level="INFO"
    )
    logger.add(
        f"logs/{date}_server.log", format=fmt, level="INFO",
        colorize=False, rotation="1 day"
    )
    logger.add(
        f"logs/{date}_server.err", format=fmt, level="ERROR",
        colorize=False, rotation="1 day"
    )

SECRET_KEY = ""
if os.path.exists("cert/session.key"):
    with open("cert/session.key", "r") as f:
        SECRET_KEY = f.read().strip()

if len(SECRET_KEY) == 0:
    SECRET_KEY = str(uuid.uuid4())
    with open("cert/session.key", "w") as f:
        f.write(SECRET_KEY)


EMAIL_SENDER = os.environ["EMAIL_SENDER"]

htmx = HTMX()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
serializer = URLSafeTimedSerializer(SECRET_KEY)

TIMEZONE = pytz.timezone(os.environ['TIMEZONE'])

db = DBHandler()
cache = Cache()
msf_cache = RedisMSFFileCache()

DOMAIN_WHITE_LIST = os.environ["DOMAIN_WHITE_LIST"].split("|")
    