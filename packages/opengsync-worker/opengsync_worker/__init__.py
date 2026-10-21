from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("opengsync-worker")
except PackageNotFoundError:
    __version__ = "0.0.0"

import os
import yaml
from pathlib import Path

from celery import Celery
from celery.schedules import crontab

config = yaml.safe_load(open("/app/opengsync.yaml"))

REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

celery = Celery("opengsync-worker", broker=f"redis://redis-cache:{REDIS_PORT}/4",)

from opengsync_worker import tasks  #  noqa
celery.autodiscover_tasks()

run_folder = Path(config["illumina_run_folder"])
upload_folder = Path(config["uploads_folder"])
upload_folder_file_age_days = config["scheduler"]["upload_folder_file_age_days"]
user_inactivity_days = config["scheduler"].get("user_inactivity_days", 365)


def parse_schedule(schedule_value):
    """Parse schedule value which could be integer (seconds) or cron string"""
    if isinstance(schedule_value, (int, float)):
        return schedule_value
    elif isinstance(schedule_value, str) and schedule_value.strip().isdigit():
        return int(schedule_value)
    elif isinstance(schedule_value, str):
        # Parse cron string
        parts = schedule_value.strip().split()
        if len(parts) == 5:
            return crontab(
                minute=parts[0],
                hour=parts[1],
                day_of_month=parts[2],
                month_of_year=parts[3],
                day_of_week=parts[4],
            )
        else:
            raise ValueError(f"Invalid cron string: {schedule_value}")
    else:
        return schedule_value


beat_schedule = {
    "rf_scan": {
        "task": "opengsync_worker.tasks.process_run_folder_wrapper",
        "schedule": parse_schedule(config["scheduler"]["rf_scan_interval_min"] * 60),
        "args": (run_folder.as_posix(),),
    },
    "status_update": {
        "task": "opengsync_worker.tasks.update_statuses_wrapper",
        "schedule": parse_schedule(config["scheduler"]["status_update_interval_min"] * 60),
        "args": (),
    },
    "clean_upload_folder": {
        "task": "opengsync_worker.tasks.clean_upload_folder_wrapper",
        "schedule": parse_schedule(config["scheduler"]["upload_folder_clean_schedule"]),
        "args": (upload_folder.as_posix(), upload_folder_file_age_days,),
    },
    "deactivate_inactive_users": {
        "task": "opengsync_worker.tasks.deactivate_inactive_users_wrapper",
        "schedule": parse_schedule(config["scheduler"].get("user_deactivation_schedule", "0 2 * * *")),
        "args": (user_inactivity_days,),
    },
}

fs_index_config = config.get("fs_index") or {}
if fs_index_config.get("enabled", False):
    beat_schedule["fs_index_import"] = {
        "task": "opengsync_worker.tasks.fs_index_import_wrapper",
        "schedule": parse_schedule(fs_index_config.get("import_schedule", 600)),
        "args": (),
    }
    beat_schedule["fs_index_crawl"] = {
        "task": "opengsync_worker.tasks.fs_index_crawl_wrapper",
        "schedule": parse_schedule(fs_index_config.get("crawl_schedule", 60)),
        "args": (),
    }

celery.conf.beat_schedule = beat_schedule