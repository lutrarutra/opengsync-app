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

from limbless_db import DBHandler, categories

from .tools import RedisMSFFileCache
from .tools.WeekTimeWindow import WeekTimeWindow

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
    SECRET_KEY = uuid.uuid4().hex
    with open("cert/session.key", "w") as f:
        f.write(SECRET_KEY)


EMAIL_SENDER = os.environ["EMAIL_SENDER"]

htmx = HTMX()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
serializer = URLSafeTimedSerializer(SECRET_KEY)

TIMEZONE = pytz.timezone(os.environ["TIMEZONE"])

db = DBHandler(logger=logger)
cache = Cache()
msf_cache = RedisMSFFileCache()

DOMAIN_WHITE_LIST = os.environ["DOMAIN_WHITE_LIST"].split("|")

sample_submission_windows: list[WeekTimeWindow] | None

if (s := os.environ["SAMPLE_SUBMISSION_WINDOWS"]):
    from .tools.tools import parse_time_windows
    sample_submission_windows = parse_time_windows(s)
    for window in sample_submission_windows:
        logger.info(f"Sample submission window: {window.weekday} {window.start_time} - {window.end_time}")
else:
    sample_submission_windows = None
    logger.warning("No sample submission windows configured..")


def update_index_kits(
    db: DBHandler, app_data_folder: str,
    types: list[categories.IndexTypeEnum] = categories.IndexType.as_list()
):
    import pandas as pd
    if not os.path.exists(os.path.join(app_data_folder, "kits")):
        os.makedirs(os.path.join(app_data_folder, "kits"))
    for type in types:
        res = []
        for kit in db.get_index_kits(limit=None, sort_by="id", descending=True, type_in=[type])[0]:
            df = db.get_index_kit_barcodes_df(kit.id, per_index=True)
            df["kit_id"] = kit.id
            df["kit"] = kit.identifier
            res.append(df)

        if len(res) == 0:
            logger.warning(f"No barcodes found for index kit type: {type.id} ({type.name})")
            continue

        pd.concat(res).to_pickle(os.path.join(app_data_folder, "kits", f"{type.id}.pkl"))
        logger.info(f"Updated index kit barcodes for type: {type.id} ({type.name})")