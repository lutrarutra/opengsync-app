import os
import traceback
import yaml
from pathlib import Path

from loguru import logger

from opengsync_db import SyncDBHandler

from opengsync_worker import celery
from opengsync_worker.tasks.clean_upload_folder import clean_upload_folder
from opengsync_worker.tasks.deactivate_inactive_users import deactivate_inactive_users
from opengsync_worker.tasks.rf_scanner import process_run_folder
from opengsync_worker.tasks.status_updater import update_statuses
from opengsync_worker.tasks.fs_index_common import FsIndexSettings
from opengsync_worker.tasks.fs_index_crawl import crawl as crawl_fs_index
from opengsync_worker.tasks.fs_index_import import import_dumps as import_fs_index_dumps

logger.remove()

config = yaml.safe_load(open("/app/opengsync.yaml"))
logdir = Path(config["log_folder"])

date = "{time:YYYY-MM-DD}"
logger.add(logdir / f"{date}.log", level="INFO", colorize=False, rotation="1 day")
logger.add(logdir / f"{date}.err", level="ERROR", colorize=False, rotation="1 day")


def connect() -> SyncDBHandler:
    db = SyncDBHandler(logger=logger)
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
        db.close_session(rollback=rollback, commit=True)


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
        db.close_session(rollback=rollback, commit=True)


@celery.task
def clean_upload_folder_wrapper(upload_folder: str, upload_folder_file_age_days: int):
    logger.info("Starting upload folder cleanup task...")
    try:
        clean_upload_folder(directory=Path(upload_folder), days_old=upload_folder_file_age_days)
    except Exception as e:
        logger.error(f"\n-------- Exception [ clean_upload_folder ] --------\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")


@celery.task
def deactivate_inactive_users_wrapper(inactivity_days: int):
    db = connect()
    rollback = False
    logger.info("Starting inactive user deactivation task...")
    try:
        db.open_session()
        deactivate_inactive_users(db, inactivity_days)
    except Exception as e:
        logger.error(f"\n-------- Exception [ deactivate_inactive_users ] --------\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
        rollback = True
    finally:
        db.close_session(rollback=rollback, commit=True)


# Redis set of directories the app just listed live (server/utils/fs_index.py), checked first by the next crawl
FS_INDEX_TOUCH_KEY = "fs-index:touch"
FS_INDEX_LOCK_KEY = "fs-index:writer-lock"
FS_INDEX_TOUCH_BATCH = 1000


def _redis():
    import redis
    return redis.Redis(host=os.environ.get("REDIS_HOST", "redis-cache"), port=int(os.environ.get("REDIS_PORT", "6379")))


def _with_fs_index_lock(name: str, ttl_s: int, func):
    """The import and the crawl both write the index; beat doesn't skip a run while the previous one is busy."""
    client = _redis()
    token = os.urandom(8).hex()
    if not client.set(FS_INDEX_LOCK_KEY, token, nx=True, ex=ttl_s):
        logger.info(f"fs-index: {name} skipped, another fs-index task is running")
        return None
    try:
        return func(client)
    except Exception as e:
        logger.error(f"\n-------- Exception [ fs_index {name} ] --------\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
    finally:
        if client.get(FS_INDEX_LOCK_KEY) == token.encode():
            client.delete(FS_INDEX_LOCK_KEY)


@celery.task
def fs_index_import_wrapper():
    settings = FsIndexSettings.from_config(config)
    # a full import of all roots can take tens of minutes
    return _with_fs_index_lock("import", 4 * 3600, lambda _: import_fs_index_dumps(settings))


@celery.task
def fs_index_crawl_wrapper():
    settings = FsIndexSettings.from_config(config)

    def run(client):
        touched = [p.decode("utf-8", "replace") for p in client.spop(FS_INDEX_TOUCH_KEY, FS_INDEX_TOUCH_BATCH) or []]
        stats = crawl_fs_index(settings, touched=touched)
        if stats["checked"]:
            logger.info(f"fs-index: crawl {stats}")
        return stats

    return _with_fs_index_lock("crawl", settings.crawl_budget_s + 300, run)
