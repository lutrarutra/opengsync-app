import sys, os

from loguru import logger
from flask_htmx import HTMX

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

htmx = HTMX()