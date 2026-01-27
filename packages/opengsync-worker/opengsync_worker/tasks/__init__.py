import os
import traceback
import yaml
from pathlib import Path

from loguru import logger

from opengsync_db import DBHandler

from opengsync_worker import celery
from opengsync_worker.tasks.clean_upload_folder import clean_upload_folder
from opengsync_worker.tasks.rf_scanner import process_run_folder
from opengsync_worker.tasks.status_updater import update_statuses

logger.remove()

config = yaml.safe_load(open("/app/opengsync.yaml"))
logdir = Path(config["log_folder"])

date = "{time:YYYY-MM-DD}"
logger.add(logdir / f"{date}.log", level="INFO", colorize=False, rotation="1 day")
logger.add(logdir / f"{date}.err", level="ERROR", colorize=False, rotation="1 day")


def connect() -> DBHandler:
    db = DBHandler(logger=logger, auto_commit=True)
    db.connect(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        db=os.environ["POSTGRES_DB"],
    )
    return db


@celery.task
def process_run_folder_wrapper(run_folder: str):
    db = connect()
    rollback = False
    logger.info("Starting run folder processing task...")
    try:
        db.open_session()
        process_run_folder(Path(run_folder), db)
    except Exception as e:
        logger.error(f"\n-------- Exception [ process_run_folder ] --------\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
        rollback = True
    finally:
        db.close_session(rollback=rollback)


@celery.task
def update_statuses_wrapper():
    db = connect()
    rollback = False
    logger.info("Starting status update task...")
    try:
        db.open_session()
        update_statuses(db)
    except Exception as e:
        logger.error(f"\n-------- Exception [ update_statuses ] --------\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
        rollback = True
    finally:
        db.close_session(rollback=rollback)


@celery.task
def clean_upload_folder_wrapper(upload_folder: str, upload_folder_file_age_days: int):
    logger.info("Starting upload folder cleanup task...")
    try:
        clean_upload_folder(directory=Path(upload_folder), days_old=upload_folder_file_age_days)
    except Exception as e:
        logger.error(f"\n-------- Exception [ clean_upload_folder ] --------\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
