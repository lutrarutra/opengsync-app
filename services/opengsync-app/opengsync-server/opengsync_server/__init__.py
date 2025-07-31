import sys
import os
import uuid

from loguru import logger
import pandas as pd
import pytz
from flask_htmx import HTMX
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_caching import Cache
from itsdangerous import URLSafeTimedSerializer

from opengsync_db import DBHandler, categories
from .tools import RedisMSFFileCache
from .tools.WeekTimeWindow import WeekTimeWindow
from .core.wrappers import page_route, htmx_route  # noqa: F401

# Show all columns without truncation
pd.set_option('display.max_columns', None)
# Show all rows without truncation
pd.set_option('display.max_rows', None)
# Disable column width truncation (so wide columns show fully)
pd.set_option('display.max_colwidth', None)
# Optional: increase the display width of your console (characters per line)
pd.set_option('display.width', 1000)

logger.remove()

fmt = """{level} @ {time:YYYY-MM-DD HH:mm:ss} [{file}:{line} in {function}]:\n------------------------ [BEGIN LOG] ------------------------\n\n{message}\n\n------------------------ [ END LOG ] ------------------------\n"""


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

db = DBHandler(logger=logger, expire_on_commit=True)
cache = Cache()
msf_cache = RedisMSFFileCache()

DOMAIN_WHITE_LIST = os.environ["DOMAIN_WHITE_LIST"].split("|")

sample_submission_windows: list[WeekTimeWindow] | None

if (s := os.environ["SAMPLE_SUBMISSION_WINDOWS"]):
    from .tools.utils import parse_time_windows
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