import os
import time
from pathlib import Path

from . import logger


def clean_upload_folder(directory: Path, days_old: int):
    logger.info(f"Cleaning up files older than {days_old} days in {directory}")
    now = time.time()
    cutoff = now - (days_old * 86400)  # 86400 seconds in a day

    for root, dirs, files in os.walk(directory):
        for name in files:
            filepath = os.path.join(root, name)
            if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
                try:
                    os.remove(filepath)
                    logger.info(f"Deleted: {filepath}")
                except Exception as e:
                    logger.error(f"Error deleting {filepath}: {e}")