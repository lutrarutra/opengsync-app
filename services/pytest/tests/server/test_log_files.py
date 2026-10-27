import gzip
import json
import multiprocessing
import os
from datetime import date, timedelta

import pytest
from loguru import logger

from server.core import audit_reader, log_files


@pytest.fixture
def add_sink():
    sink_ids = []

    def add(sink: log_files.DailyFileSink) -> None:
        sink_ids.append(logger.add(sink, format="{message}", filter=lambda r: r["extra"].get("test_log_files")))

    yield add
    for sink_id in sink_ids:
        logger.remove(sink_id)


def _write_lines(folder: str, worker: int, n: int) -> None:
    logger.remove()
    logger.add(log_files.DailyFileSink(folder, ".jsonl"), format="{message}")
    for i in range(n):
        logger.info(json.dumps({"worker": worker, "i": i, "pad": "x" * 2000}))


def test_sink_writes_to_the_records_date(tmp_path, add_sink):
    add_sink(log_files.DailyFileSink(str(tmp_path), ".jsonl"))
    today = date.today()
    logger.bind(test_log_files=True).info("first")
    with logger.contextualize(test_log_files=True):
        logger.patch(lambda r: r.update(time=r["time"] - timedelta(days=3))).info("old")

    assert (tmp_path / f"{today}.jsonl").read_text() == "first\n"
    assert (tmp_path / f"{today - timedelta(days=3)}.jsonl").read_text() == "old\n"


def test_concurrent_processes_lose_no_lines(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_write_lines, args=(str(tmp_path), w, 300)) for w in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
        assert p.exitcode == 0

    lines = (tmp_path / f"{date.today()}.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in lines]
    assert sorted((r["worker"], r["i"]) for r in records) == [(w, i) for w in range(4) for i in range(300)]


def test_compress_skips_today_and_yesterday(tmp_path):
    today = date(2026, 10, 27)
    for days in range(4):
        (tmp_path / f"{today - timedelta(days=days)}.jsonl").write_text(f'{{"ts": "{days}"}}\n')
    # an archive left by loguru's old rotation, under the name the new one would get
    (tmp_path / "2026-10-24.jsonl.gz").write_bytes(gzip.compress(b'{"ts": "old"}\n'))

    compressed = log_files.compress_old_files(str(tmp_path), ".jsonl", before=today - timedelta(days=1))

    assert sorted(os.path.basename(p) for p in compressed) == ["2026-10-24.1.jsonl.gz", "2026-10-25.jsonl.gz"]
    assert sorted(os.listdir(tmp_path)) == [
        "2026-10-24.1.jsonl.gz", "2026-10-24.jsonl.gz", "2026-10-25.jsonl.gz", "2026-10-26.jsonl", "2026-10-27.jsonl",
    ]
    assert gzip.decompress((tmp_path / "2026-10-24.1.jsonl.gz").read_bytes()) == b'{"ts": "3"}\n'
    # the reader still finds every file by the date at the start of its name
    assert len(audit_reader.audit_files(str(tmp_path), since=date(2026, 10, 24))) == 5


def test_delete_old_files_keeps_other_suffixes(tmp_path):
    for name in [
        "2026-10-19.log", "2026-10-19.2026-10-19_00-00-01_000000.log.zip", "2026-10-19.err",
        "2026-10-20.log.gz", "2026-10-21.log",
    ]:
        (tmp_path / name).write_text("x")

    log_files.delete_old_files(str(tmp_path), ".log", before=date(2026, 10, 21))

    assert sorted(os.listdir(tmp_path)) == ["2026-10-19.err", "2026-10-21.log"]


def test_housekeep_compresses_and_applies_retention(tmp_path):
    sink = log_files.DailyFileSink(str(tmp_path), ".log", retention_days=7)
    today = date(2026, 10, 27)
    for days in (0, 1, 2, 8):
        (tmp_path / f"{today - timedelta(days=days)}.log").write_text("x\n")

    sink.housekeep(today)

    assert sorted(n for n in os.listdir(tmp_path) if not n.startswith(".")) == [
        "2026-10-25.log.gz", "2026-10-26.log", "2026-10-27.log",
    ]
