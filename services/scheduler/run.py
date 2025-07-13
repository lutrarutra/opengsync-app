import argparse
import os
import atexit
import time

from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from opengsync_db.core import DBHandler

from scheduler.rf_scanner import process_run_folder
from scheduler.status_updater import update_statuses
from scheduler.file_cleaner import clean_upload_folder


def connect() -> DBHandler:
    db = DBHandler()
    db.connect(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        db=os.environ["POSTGRES_DB"],
    )
    return db


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-folder", type=str)
    parser.add_argument("--rf-scan-interval", type=int)
    parser.add_argument("--status-update-interval", type=int)
    parser.add_argument("--upload-folder", type=str)
    parser.add_argument("--upload-folder-file-age-days", type=int)
    parser.add_argument("--upload-folder-clean-schedule", type=str, default="0 0 1 * * *")
    
    args = parser.parse_args()

    if not os.path.exists(args.run_folder):
        raise FileNotFoundError(f"Run folder not found: {args.run_folder}")

    scheduler = BlockingScheduler()
        
    def process_run_folder_wrapper():
        db = connect()
        db.open_session()
        process_run_folder(args.run_folder, db)
        db.close_session()

    def update_statuses_wrapper():
        db = connect()
        db.open_session()
        update_statuses(db)
        db.close_session()

    def clean_upload_folder_wrapper():
        clean_upload_folder(directory=args.upload_folder, days_old=args.upload_folder_file_age_days)

    scheduler.add_job(func=process_run_folder_wrapper, trigger="interval", minutes=args.rf_scan_interval, id="process_run_folder", replace_existing=True)
    time.sleep(30)
    scheduler.add_job(func=update_statuses_wrapper, trigger="interval", minutes=args.status_update_interval, id="update_statuses", replace_existing=True)
    time.sleep(15)
    second, minute, hour, day, month, day_of_week = args.upload_folder_clean_schedule.split()
    trigger = CronTrigger(second=second, minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
    scheduler.add_job(func=clean_upload_folder_wrapper, trigger=trigger, id="clean_upload_folder", replace_existing=True)

    atexit.register(lambda: scheduler.shutdown())

    scheduler.start()


if __name__ == "__main__":
    cli()

exit(0)