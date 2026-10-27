"""Daily log files that several processes can write at once.

Gunicorn runs several workers, and during a deploy the old and new container overlap, all writing the same files.
Loguru's own rotation and compression only work within one process: the workers race to rotate the file, which drops
the record that triggered a failed rotation and leaves renamed archives behind. And its `rotation="1 day"` means 24
hours after the file was created, not midnight.

Instead, `DailyFileSink` appends each line to the file named by the record's own (local) date, opened with `O_APPEND`,
so concurrent single-line writes from different processes don't overwrite or interleave. Older files are compressed by
`compress_old_files`, run by whichever process first logs on a new day (and at startup) and serialised with a lock file.
"""
import fcntl
import gzip
import os
import re
import shutil
import threading
from datetime import date, datetime, timedelta

from loguru import logger

DATE_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(.*)$")


class DailyFileSink:
    """Loguru sink writing to `{folder}/YYYY-MM-DD{suffix}` by the record's date.

    `compress_after_days` compresses files that many days old (gzip, `{name}.gz`), `retention_days` deletes files
    older than that, plain or compressed. Yesterday's file is left alone, a write from just before midnight may still
    be on its way.
    """

    def __init__(self, folder: str, suffix: str, compress_after_days: int = 2, retention_days: int | None = None):
        if compress_after_days < 2:
            raise ValueError("compress_after_days must be at least 2")
        self.folder = folder
        self.suffix = suffix
        self.compress_after_days = compress_after_days
        self.retention_days = retention_days
        self._day: date | None = None
        self._fd: int | None = None
        os.makedirs(folder, exist_ok=True)
        self._housekeep_in_background(datetime.now().astimezone().date())

    def __call__(self, message) -> None:
        # loguru calls a sink under its handler lock, so there is one call at a time per process
        day = message.record["time"].date()
        if day != self._day or self._fd is None:
            if self._fd is not None:
                os.close(self._fd)
            self._fd = os.open(self.path(day), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            if self._day is not None and day > self._day:
                self._housekeep_in_background(day)
            self._day = day
        # one write() per line, so a line is never split around another process's line
        os.write(self._fd, str(message).encode("utf-8"))

    def path(self, day: date) -> str:
        return os.path.join(self.folder, f"{day.isoformat()}{self.suffix}")

    def _housekeep_in_background(self, today: date) -> None:
        threading.Thread(target=self.housekeep, args=(today,), daemon=True, name=f"log-housekeeping{self.suffix}").start()

    def housekeep(self, today: date) -> None:
        """Compress and delete old files, unless another process is already doing it."""
        try:
            with open(os.path.join(self.folder, f".housekeeping{self.suffix}.lock"), "w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
                compress_old_files(self.folder, self.suffix, before=today - timedelta(days=self.compress_after_days - 1))
                if self.retention_days is not None:
                    delete_old_files(self.folder, self.suffix, before=today - timedelta(days=self.retention_days))
        except Exception as e:
            logger.error(f"Log housekeeping in {self.folder} for '{self.suffix}' failed: {e!r}")


def _dated_files(folder: str, suffix: str):
    """(date, name) of the files in `folder` named `YYYY-MM-DD...` that contain `suffix` after the date."""
    for name in os.listdir(folder):
        if not (m := DATE_NAME_RE.match(name)) or suffix not in m.group(2):
            continue
        try:
            yield date.fromisoformat(m.group(1)), name
        except ValueError:
            continue


def compress_old_files(folder: str, suffix: str, before: date) -> list[str]:
    """Gzip every plain `YYYY-MM-DD{suffix}` file dated before `before`. Returns the compressed files' new paths.

    If `{name}.gz` already exists (from loguru's old rotation), the new archive is `YYYY-MM-DD.N{suffix}.gz` instead,
    so the date stays the first 10 characters of the name.
    """
    compressed = []
    for file_date, name in _dated_files(folder, suffix):
        if file_date >= before or name != f"{file_date.isoformat()}{suffix}":
            continue
        src = os.path.join(folder, name)
        dst = f"{src}.gz"
        n = 1
        while os.path.exists(dst):
            dst = os.path.join(folder, f"{file_date.isoformat()}.{n}{suffix}.gz")
            n += 1
        tmp = f"{dst}.tmp"
        with open(src, "rb") as f_in, gzip.open(tmp, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.replace(tmp, dst)
        os.remove(src)
        compressed.append(dst)
    return compressed


def delete_old_files(folder: str, suffix: str, before: date) -> list[str]:
    """Delete every `YYYY-MM-DD...{suffix}...` file dated before `before`, compressed or not."""
    deleted = []
    for file_date, name in _dated_files(folder, suffix):
        if file_date < before:
            os.remove(path := os.path.join(folder, name))
            deleted.append(path)
    return deleted
