import sys, os

from loguru import logger
from flask_htmx import HTMX
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer

logger.remove()

fmt = """{level} @ {time:YYYY-MM-DD HH:mm:ss} ({file}:{line} in {function}):
>   {message}"""

if os.getenv("FLASK_DEBUG") == "1":
    logger.add(
        sys.stdout, colorize=True,
        format=fmt, level="DEBUG"
    )
else:
    logger.add(
        sys.stdout, colorize=True,
        format=fmt, level="INFO"
    )


SECRET_KEY = "SECRET_KEY"
EMAIL_SENDER = "noreply@limbless.com"
htmx = HTMX()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
serializer = URLSafeTimedSerializer(SECRET_KEY)
