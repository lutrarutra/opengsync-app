"""fs-index: cluster dump -> import -> mtime-driven crawler, on a real tree under tmp_path."""
import gzip
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

DUMP_SCRIPT = Path(os.environ.get("FS_INDEX_DUMP_SCRIPT", "/app/tools/fs_index_dump.py"))
NOW = 2_000_000_000
DAY = 24 * 3600


@pytest.fixture
def tasks(import_worker_task):
    common = import_worker_task("fs_index_common")
    return common, import_worker_task("fs_index_import"), import_worker_task("fs_index_crawl")


def _write(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


@pytest.fixture
def share(tmp_path: Path) -> Path:
    """
    share/
      R1/
        .ngsignore                      "hidden/"
        .DS_Store                       junk, never stored
        proj/outs/a.bam                 100
        proj/SC_RNA_COUNTER_CS/c/x.bin  50   opaque: counted, not stored
        proj/link.bin -> ../../R2/x/big.bin   counts the target (1000)
        proj/escape -> <outside>        unsafe
        hidden/s.txt                    7    hidden by .ngsignore, not counted
      R2/x/big.bin                      1000
    """
    root = tmp_path / "share"
    _write(root / "R1" / "proj" / "outs" / "a.bam", 100)
    _write(root / "R1" / "proj" / "SC_RNA_COUNTER_CS" / "c" / "x.bin", 50)
    _write(root / "R1" / "hidden" / "s.txt", 7)
    _write(root / "R1" / ".DS_Store", 1)
    (root / "R1" / ".ngsignore").write_text("hidden/\n")
    _write(root / "R2" / "x" / "big.bin", 1000)
    (root / "R1" / "proj" / "link.bin").symlink_to("../../R2/x/big.bin")
    outside = _write(tmp_path / "outside" / "leak.txt", 3).parent
    (root / "R1" / "proj" / "escape").symlink_to(outside, target_is_directory=True)
    # well before the dump, so later changes get a different mtime (1 s resolution)
    old = time.time() - 1000
    for path in [root, *root.rglob("*")]:
        os.utime(path, (old, old), follow_symlinks=False)
    return root


@pytest.fixture
def settings(tasks, tmp_path: Path, share: Path):
    common, _, _ = tasks
    return common.FsIndexSettings(
        db_file=str(tmp_path / "app_data" / "fs_index.sqlite3"),
        dump_dir=str(tmp_path / "dumps"),
        share_root=str(share),
        crawl_threads=2,
    )


def dump(settings, *roots: str) -> None:
    if not DUMP_SCRIPT.exists():
        pytest.skip(f"{DUMP_SCRIPT} not mounted")
    args = [sys.executable, str(DUMP_SCRIPT), "--out", settings.dump_dir, "--threads", "2"]
    for root in roots:
        args += ["--root", f"{root}={Path(settings.share_root) / root}"]
    subprocess.run(args, check=True, capture_output=True)


def rows(settings) -> dict[str, dict]:
    conn = sqlite3.connect(settings.db_file)
    conn.row_factory = sqlite3.Row
    try:
        return {row["path"]: dict(row) for row in conn.execute("SELECT * FROM entry")}
    finally:
        conn.close()


def search(settings, term: str) -> list[str]:
    conn = sqlite3.connect(settings.db_file)
    try:
        return sorted(path for (path,) in conn.execute(
            "SELECT e.path FROM entry_fts JOIN entry e ON e.id = entry_fts.rowid WHERE entry_fts MATCH ?",
            (f'"{term}"',),
        ))
    finally:
        conn.close()


def totals(entries: dict[str, dict], path: str) -> tuple[int, int]:
    return entries[path]["total_size"], entries[path]["n_files"]


# ── import ──────────────────────────────────────────────────────────────────


def test_import_stores_entries_flags_and_totals(tasks, settings):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    stats = importer.import_dumps(settings, now=NOW)
    assert sorted(s["root"] for s in stats) == ["R1", "R2"]

    entries = rows(settings)
    assert "R1/.DS_Store" not in entries
    # opaque: the directory is stored and counted, its contents are not stored or searchable
    cs = entries["R1/proj/SC_RNA_COUNTER_CS"]
    assert (cs["opaque"], cs["searchable"], cs["next_check_at"]) == (1, 0, None)
    assert totals(entries, "R1/proj/SC_RNA_COUNTER_CS") == (50, 1)
    assert not any(path.startswith("R1/proj/SC_RNA_COUNTER_CS/") for path in entries)

    assert entries["R1/hidden"]["hidden"] == 1
    assert entries["R1/hidden/s.txt"]["hidden"] == 1
    assert entries["R1/.ngsignore"]["hidden"] == 1
    assert totals(entries, "R1/hidden") == (0, 0)

    assert entries["R1/proj/link.bin"]["link_target"] == "R2/x/big.bin"
    assert entries["R1/proj/escape"]["unsafe"] == 1

    # 100 (a.bam) + 50 (opaque) + 1000 (link to a file); hidden and the unsafe link don't count
    assert totals(entries, "R1/proj") == (1150, 3)
    assert totals(entries, "R1") == (1150, 3)
    assert totals(entries, "R2") == (1000, 1)
    assert entries["R1/proj/outs/a.bam"]["parent_id"] == entries["R1/proj/outs"]["id"]
    assert entries["R1"]["parent_id"] is None

    assert search(settings, "big") == ["R2/x/big.bin"]
    assert search(settings, "a.ba") == ["R1/proj/outs/a.bam"]


def test_unchanged_dumps_are_not_imported_again(tasks, settings):
    _, importer, _ = tasks
    dump(settings, "R1")
    assert importer.import_dumps(settings, now=NOW)
    assert importer.import_dumps(settings, now=NOW) == []


def test_new_dump_replaces_its_root_only(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)

    (share / "R1" / "proj" / "outs" / "a.bam").unlink()
    _write(share / "R1" / "new.txt", 5)
    dump(settings, "R1")
    os.utime(Path(settings.dump_dir) / "R1.jsonl.gz", (NOW, NOW))  # a new signature even within the same second
    [stats] = importer.import_dumps(settings, now=NOW)
    assert stats["root"] == "R1"

    entries = rows(settings)
    assert "R1/proj/outs/a.bam" not in entries
    assert "R1/new.txt" in entries
    assert "R2/x/big.bin" in entries
    assert search(settings, "big") == ["R2/x/big.bin"]
    assert search(settings, "a.bam") == []


def test_incomplete_dump_is_skipped(tasks, settings):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    path = Path(settings.dump_dir) / "R2.jsonl.gz"
    lines = gzip.decompress(path.read_bytes()).splitlines(keepends=True)
    path.write_bytes(gzip.compress(b"".join(lines[:-1])))  # drop the footer

    stats = importer.import_dumps(settings, now=NOW)
    assert [s["root"] for s in stats] == ["R1"]
    assert not any(p.startswith("R2") for p in rows(settings))


def test_dirs_are_seeded_by_age(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1")
    created = int(os.stat(share / "R1" / "proj" / "outs").st_mtime)
    importer.import_dumps(settings, now=created + 3600)
    assert rows(settings)["R1/proj/outs"]["check_interval"] == settings.min_interval_s

    os.utime(Path(settings.dump_dir) / "R1.jsonl.gz", (NOW, NOW))
    importer.import_dumps(settings, now=created + 365 * DAY)
    assert rows(settings)["R1/proj/outs"]["check_interval"] == settings.max_interval_s


# ── crawl ───────────────────────────────────────────────────────────────────


def _crawl(tasks, settings, at: int, **kwargs):
    _, _, crawler = tasks
    return crawler.crawl(settings, now=at, **kwargs)


def test_crawl_picks_up_changes_and_keeps_totals(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)

    _write(share / "R1" / "proj" / "outs" / "new.txt", 30)
    _write(share / "R1" / "proj" / "newdir" / "deep" / "f", 5)
    (share / "R2" / "x" / "big.bin").unlink()

    stats = _crawl(tasks, settings, NOW + 30 * DAY)
    assert stats["changed"] >= 3
    conn = sqlite3.connect(settings.db_file)
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    conn.close()
    assert json.loads(meta["last_crawl"])["changed"] == stats["changed"]
    assert meta["last_change_at"] == str(NOW + 30 * DAY)
    assert json.loads(meta["import_stats:R1"])["file"] == "R1.jsonl.gz"

    entries = rows(settings)
    assert "R1/proj/outs/new.txt" in entries
    assert "R1/proj/newdir/deep/f" in entries  # new directories are listed in the same run
    assert "R2/x/big.bin" not in entries
    assert totals(entries, "R1/proj/outs") == (130, 2)
    # 130 (2 files) + 5 (newdir) + 50 (opaque); the link's target is gone
    assert totals(entries, "R1/proj") == (185, 4)
    assert totals(entries, "R1") == (185, 4)
    assert totals(entries, "R2") == (0, 0)
    assert search(settings, "new.txt") == ["R1/proj/outs/new.txt"]


def test_unchanged_directories_back_off(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1")
    created = int(os.stat(share / "R1" / "proj" / "outs").st_mtime)
    importer.import_dumps(settings, now=created)  # recent: checked every min_interval_s

    at = created + settings.min_interval_s + 1
    _crawl(tasks, settings, at)
    first = rows(settings)["R1/proj/outs"]
    assert first["check_interval"] == 2 * settings.min_interval_s
    assert first["next_check_at"] == at + first["check_interval"]

    _crawl(tasks, settings, first["next_check_at"])
    assert rows(settings)["R1/proj/outs"]["check_interval"] == 4 * settings.min_interval_s

    # a change resets it
    _write(share / "R1" / "proj" / "outs" / "b.txt", 1)
    _crawl(tasks, settings, first["next_check_at"] + 10 * settings.min_interval_s)
    assert rows(settings)["R1/proj/outs"]["check_interval"] == settings.min_interval_s


def test_edited_ignore_file_is_picked_up_without_dir_mtime_change(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)

    ignore = share / "R1" / ".ngsignore"
    dir_mtime = os.stat(share / "R1").st_mtime
    ignore.write_text("# nothing hidden\n")
    os.utime(ignore, (1, 1))
    os.utime(share / "R1", (dir_mtime, dir_mtime))

    _crawl(tasks, settings, NOW + 1)
    entries = rows(settings)
    assert entries["R1/hidden"]["hidden"] == 0
    assert entries["R1/hidden/s.txt"]["hidden"] == 0
    assert totals(entries, "R1") == (1157, 4)


def test_offline_root_is_not_emptied(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1")
    importer.import_dumps(settings, now=NOW)
    settings.canaries = {"R1": "R1/.status.txt"}  # missing: the mount counts as down

    for child in (share / "R1" / "proj").iterdir():
        if child.is_dir() and not child.is_symlink():
            os.rename(child, share.parent / f"moved-{child.name}")

    _crawl(tasks, settings, NOW + 30 * DAY)
    assert "R1/proj/outs/a.bam" in rows(settings)


def test_crawler_builds_an_index_without_a_dump(tasks, settings):
    stats = _crawl(tasks, settings, NOW)
    assert stats["added"] > 0
    entries = rows(settings)
    assert "R1/proj/outs/a.bam" in entries
    assert entries["R1/proj/SC_RNA_COUNTER_CS"]["opaque"] == 1
    assert entries["R1/hidden/s.txt"]["hidden"] == 1
    assert totals(entries, "R1") == (1100, 2)  # an opaque dir found by the crawler has no totals


def test_touched_unknown_directory_is_discovered(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1")
    importer.import_dumps(settings, now=NOW)
    # created inside an unchanged directory listing: only the touch makes the crawler look
    _write(share / "R1" / "proj" / "outs" / "fresh" / "x.txt", 1)
    outs = share / "R1" / "proj" / "outs"
    os.utime(outs, (rows(settings)["R1/proj/outs"]["mtime"],) * 2)

    _crawl(tasks, settings, NOW + 1)
    assert "R1/proj/outs/fresh/x.txt" not in rows(settings)
    _crawl(tasks, settings, NOW + 2, touched=["R1/proj/outs/fresh"])
    assert "R1/proj/outs/fresh/x.txt" in rows(settings)


def test_settings_from_config(tasks):
    common, _, _ = tasks
    settings = common.FsIndexSettings.from_config({
        "share_root": "/share",
        "app_data_folder": "/app_data",
        "canary_files": {"bsf_projects": "/share/BSF_PROJECTS/.status.txt", "elsewhere": "/tmp/x"},
        "fs_index": {"enabled": True, "crawl_budget_s": 10, "index_ignore": ["tmp"]},
    })
    assert settings.db_file == "/app_data/fs_index/fs_index.sqlite3"
    assert settings.dump_dir == "/app_data/fs_index/dumps"
    assert settings.canaries == {"BSF_PROJECTS": "BSF_PROJECTS/.status.txt"}
    assert settings.crawl_budget_s == 10
    assert settings.crawl_rate == 10 and settings.crawl_threads == 1  # defaults
    assert settings.is_index_ignored("tmp") and not settings.is_index_ignored("work")


def test_dump_records_symlinks_and_ignore_files(settings):
    dump(settings, "R1")
    lines = [json.loads(line) for line in gzip.decompress((Path(settings.dump_dir) / "R1.jsonl.gz").read_bytes()).splitlines()]
    assert lines[0]["kind"] == "header" and lines[-1]["kind"] == "footer"
    entries = {line[0]: line for line in lines if isinstance(line, list)}
    assert entries["proj/link.bin"][1] == "l"
    assert entries["proj/link.bin"][6:8] == ["f", 1000]
    assert {"kind": "ignore", "path": ".ngsignore", "content": "hidden/\n"} in lines


def test_rate_limit_spaces_out_folder_checks(tasks, settings):
    _, importer, crawler = tasks
    dump(settings, "R1")
    importer.import_dumps(settings, now=NOW)
    settings.crawl_rate = 20  # 50 ms per folder

    started = time.monotonic()
    stats = crawler.crawl(settings, now=NOW + 30 * DAY)
    elapsed = time.monotonic() - started
    # R1's folders, plus R2 and R2/x, which the crawler finds on disk itself (only R1 was dumped)
    assert stats["checked"] == sum(1 for e in rows(settings).values() if e["kind"] == "d" and not e["opaque"])
    assert elapsed >= (stats["checked"] - 1) / settings.crawl_rate


def test_rate_limiter_is_shared_by_threads(tasks):
    _, _, crawler = tasks
    limiter = crawler.RateLimiter(100)
    started = time.monotonic()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: limiter.wait(), range(20)))
    assert time.monotonic() - started >= 0.18
    assert crawler.RateLimiter(0).interval == 0
