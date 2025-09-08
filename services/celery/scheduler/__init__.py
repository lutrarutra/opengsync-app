
import os
import yaml
from pathlib import Path

from celery import Celery
from celery.schedules import crontab

config = yaml.safe_load(open("/usr/src/app/opengsync.yaml"))

REDIS_PORT = int(os.environ["REDIS_PORT"])

celery = Celery("scheduler", broker=f"redis://redis-cache:{REDIS_PORT}/4",)

from scheduler import tasks  # noqa: E402, F401
celery.autodiscover_tasks()

run_folder = Path(config["illumina_run_folder"])
upload_folder = Path(config["uploads_folder"])
upload_folder_file_age_days = config["scheduler"]["upload_folder_file_age_days"]


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
        "task": "scheduler.tasks.process_run_folder_wrapper",
        "schedule": parse_schedule(config["scheduler"]["rf_scan_interval_min"] * 60),
        "args": (run_folder.as_posix(),),
    },
    "status_update": {
        "task": "scheduler.tasks.update_statuses_wrapper",
        "schedule": parse_schedule(config["scheduler"]["status_update_interval_min"] * 60),
        "args": (),
    },
    "clean_upload_folder": {
        "task": "scheduler.tasks.clean_upload_folder_wrapper",
        "schedule": parse_schedule(config["scheduler"]["upload_folder_clean_schedule"]),
        "args": (upload_folder.as_posix(), upload_folder_file_age_days,),
    },
}

celery.conf.beat_schedule = beat_schedule