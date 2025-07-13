import sys
import os

from loguru import logger


logger.remove()

fmt = """{level} @ {time:YYYY-MM-DD HH:mm:ss} ({file}:{line} in {function}):
>   {message}"""


if os.getenv("OPENGSYNC_DEBUG") == "1":
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
        f"logs/{date}_scheduler.log", format=fmt, level="INFO",
        colorize=False, rotation="1 day"
    )
    logger.add(
        f"logs/{date}_scheduler.err", format=fmt, level="ERROR",
        colorize=False, rotation="1 day"
    )
