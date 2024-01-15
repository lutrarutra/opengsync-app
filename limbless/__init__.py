import sys
import os

from loguru import logger
from flask_htmx import HTMX
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer

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
        f"logs/limbless_{date}.log", format=fmt, level="INFO",
        colorize=False, rotation="1 day"
    )
    logger.add(
        f"logs/limbless_{date}.err", format=fmt, level="ERROR",
        colorize=False, rotation="1 day"
    )

PAGE_LIMIT = 15
SECRET_KEY = "SECRET_KEY"
if (SEQ_AUTH_FORMS_DIR := os.getenv("SEQ_AUTH_FORMS_DIR")) is None:
    SEQ_AUTH_FORMS_DIR = ""
    raise ValueError("SEQ_AUTH_FORMS_DIR environment variable not set")

if not os.path.exists(SEQ_AUTH_FORMS_DIR):
    os.mkdir(SEQ_AUTH_FORMS_DIR)

if (EMAIL_SENDER := os.getenv("EMAIL_SENDER")) is None:
    EMAIL_SENDER = ""
    raise ValueError("EMAIL_SENDER environment variable not set")

htmx = HTMX()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
serializer = URLSafeTimedSerializer(SECRET_KEY)