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
    # a dump that follows a symlink cycle never finishes: fail instead of hanging the suite
    subprocess.run(args, check=True, capture_output=True, timeout=120)


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


def test_missing_root_is_not_emptied(tasks, settings, share: Path):
    _, importer, _ = tasks
    dump(settings, "R1")
    importer.import_dumps(settings, now=NOW)
    os.rename(share / "R1", share.parent / "R1-unmounted")

    _crawl(tasks, settings, NOW + 30 * DAY)
    assert "R1/proj/outs/a.bam" in rows(settings)


def test_listing_taken_while_mount_was_away_removes_nothing(tasks, settings, share: Path, monkeypatch):
    """The mount drops during a listing and is back by the time it is applied: the online check passes."""
    _, importer, crawler = tasks
    dump(settings, "R1")
    importer.import_dumps(settings, now=NOW)
    proj, away = share / "R1" / "proj", share.parent / "away"
    real_probe = crawler.Crawler.probe

    def flaky_probe(self, row):
        if row.path != "R1/proj":
            return real_probe(self, row)
        away.mkdir()
        for child in list(proj.iterdir()):
            os.rename(child, away / child.name)
        try:
            return real_probe(self, row)
        finally:
            for child in list(away.iterdir()):
                os.rename(child, proj / child.name)
            away.rmdir()

    monkeypatch.setattr(crawler.Crawler, "probe", flaky_probe)
    _crawl(tasks, settings, NOW + 30 * DAY)
    entries = rows(settings)
    assert "R1/proj/outs/a.bam" in entries
    assert entries["R1/proj"]["mtime"] is None  # listed again on the next run

    monkeypatch.setattr(crawler.Crawler, "probe", real_probe)
    old = time.time() - 100  # the renames just changed it: a same-second mtime is not trusted
    os.utime(proj, (old, old))
    _crawl(tasks, settings, NOW + 30 * DAY + 1)
    entries = rows(settings)
    assert "R1/proj/outs/a.bam" in entries
    assert entries["R1/proj"]["mtime"] is not None


def test_online_is_checked_again_after_the_mount_drops(tasks, settings, share: Path):
    _, _, crawler = tasks
    (share / "R1" / ".status.txt").write_text("ok")
    settings.canaries = {"R1": "R1/.status.txt"}
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE ignore_file (dir_path TEXT, content TEXT)")
        c = crawler.Crawler(conn, settings)
        assert c.is_online("R1/proj")
        (share / "R1" / ".status.txt").unlink()
        assert not c.is_online("R1/proj")
        (share / "R1" / ".status.txt").write_text("ok")
        assert not c.is_online("R1/proj")  # offline for the rest of the run
    finally:
        conn.close()


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


# ── symlinks: leaving the share, and cycles ─────────────────────────────────


def _age(root: Path, seconds_ago: int = 1000) -> None:
    old = time.time() - seconds_ago
    for path in [root, *root.rglob("*")]:
        os.utime(path, (old, old), follow_symlinks=False)


# link -> share path it resolves to; none of them may be descended into
CYCLES = {
    "R1/proj/up": "R1",                 # its own grandparent
    "R1/proj/outs/self": "R1/proj/outs",  # its own folder
    "R1/proj/to_r2": "R2/x",            # R1/proj -> R2/x -> R1/proj, across roots
    "R2/x/to_r1": "R1/proj",
}
LOOPS = ("R1/loop_a", "R1/loop_b")  # point at each other: ELOOP


@pytest.fixture
def cyclic_share(share: Path) -> Path:
    (share / "R1" / "proj" / "up").symlink_to("..", target_is_directory=True)
    (share / "R1" / "proj" / "outs" / "self").symlink_to(".", target_is_directory=True)
    (share / "R1" / "proj" / "to_r2").symlink_to("../../R2/x", target_is_directory=True)
    (share / "R2" / "x" / "to_r1").symlink_to("../../R1/proj", target_is_directory=True)
    (share / "R1" / "loop_a").symlink_to("loop_b")
    (share / "R1" / "loop_b").symlink_to("loop_a")
    _age(share)
    return share


def assert_cycles_stored_once(entries: dict[str, dict]) -> None:
    for link, target in CYCLES.items():
        assert (entries[link]["kind"], entries[link]["target_kind"]) == ("l", "d"), link
        assert entries[link]["link_target"] == target, link
        assert entries[link]["unsafe"] == 0, link
    for link in LOOPS:
        assert (entries[link]["kind"], entries[link]["target_kind"]) == ("l", "loop"), link
    for link in (*CYCLES, *LOOPS):
        assert not any(path.startswith(f"{link}/") for path in entries), f"descended into {link}"


def test_dump_records_cyclic_symlinks_without_descending(settings, cyclic_share: Path):
    dump(settings, "R1")
    lines = [json.loads(line) for line in gzip.decompress((Path(settings.dump_dir) / "R1.jsonl.gz").read_bytes()).splitlines()]
    entries = {line[0]: line for line in lines if isinstance(line, list)}
    assert entries["proj/up"][1] == "l" and entries["proj/up"][6] == "d"
    assert entries["proj/outs/self"][6] == "d"
    assert entries["loop_a"][6] == "loop" and entries["loop_b"][6] == "loop"
    assert not any(rel.startswith(("proj/up/", "proj/outs/self/", "proj/to_r2/")) for rel in entries)
    assert lines[-1]["kind"] == "footer" and lines[-1]["errors"] == 0


def test_import_stores_cyclic_symlinks_once(tasks, settings, cyclic_share: Path):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)

    entries = rows(settings)
    assert_cycles_stored_once(entries)
    # links to folders and loops add nothing: the same totals as without them
    assert totals(entries, "R1") == (1150, 3)
    assert totals(entries, "R2") == (1000, 1)
    assert search(settings, "a.bam") == ["R1/proj/outs/a.bam"]
    assert search(settings, "big") == ["R2/x/big.bin"]


def test_crawler_does_not_follow_cyclic_symlinks(tasks, settings, cyclic_share: Path):
    stats = _crawl(tasks, settings, NOW)
    assert stats["errors"] == 0

    entries = rows(settings)
    assert_cycles_stored_once(entries)
    assert totals(entries, "R1") == (1100, 2)  # as in test_crawler_builds_an_index_without_a_dump
    assert search(settings, "a.bam") == ["R1/proj/outs/a.bam"]

    # every folder changed: listing them all again finds nothing below the links either
    _age(cyclic_share, seconds_ago=500)
    _crawl(tasks, settings, NOW + 30 * DAY)
    assert rows(settings).keys() == entries.keys()


def test_recrawl_after_import_keeps_cyclic_symlinks_stable(tasks, settings, cyclic_share: Path):
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)
    before = rows(settings)

    _age(cyclic_share, seconds_ago=500)  # every folder changed: all are listed again
    stats = _crawl(tasks, settings, NOW + 30 * DAY)
    assert stats["changed"] >= 4

    entries = rows(settings)
    assert_cycles_stored_once(entries)
    assert entries.keys() == before.keys()
    for path in ("R1", "R1/proj", "R2"):
        assert totals(entries, path) == totals(before, path), path


def test_touched_path_through_a_cyclic_symlink_adds_nothing_below_it(tasks, settings, cyclic_share: Path):
    """The app touches what it listed live, and the live browser follows symlinks: these paths go through cycles."""
    _, importer, _ = tasks
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)

    touched = ["R1/proj/up/proj/up/proj/outs", "R1/proj/outs/self/self/self", "R2/x/to_r1/to_r2/to_r1"]
    stats = _crawl(tasks, settings, NOW + 1, touched=touched)
    assert stats["errors"] == 0
    assert_cycles_stored_once(rows(settings))


def test_crawler_does_not_follow_symlinks_leaving_the_share(tasks, settings):
    _crawl(tasks, settings, NOW)
    entries = rows(settings)
    escape = entries["R1/proj/escape"]
    assert (escape["kind"], escape["unsafe"], escape["link_target"], escape["target_kind"]) == ("l", 1, None, "d")
    assert not any(path.startswith("R1/proj/escape/") for path in entries)
    assert search(settings, "leak") == []


def test_symlinked_root_leaving_the_share_is_not_indexed(tasks, settings, share: Path):
    """A top-level folder of the share that is a symlink out of it, instead of a mount."""
    (share / "R3").symlink_to(share.parent / "outside", target_is_directory=True)
    _crawl(tasks, settings, NOW)
    _crawl(tasks, settings, NOW + 30 * DAY)
    entries = rows(settings)
    assert not any(path.startswith("R3/") for path in entries)
    assert search(settings, "leak") == []


def test_absolute_cluster_symlinks_become_unsafe_when_relisted(tasks, settings, share: Path, tmp_path: Path):
    """The dump resolves symlinks on the cluster, the crawler inside the container (docs/file-share.md).

    An absolute link to a cluster path is mapped onto the share by the import, but the container cannot
    resolve it: once its folder is listed again, it counts as leaving the share. Relative links keep working.
    """
    _, importer, _ = tasks
    proj = share / "R1" / "proj"
    (proj / "abs.bin").symlink_to(share / "R2" / "x" / "big.bin")  # absolute, cluster-side path
    _age(share)
    dump(settings, "R1", "R2")
    importer.import_dumps(settings, now=NOW)
    entries = rows(settings)
    assert (entries["R1/proj/abs.bin"]["link_target"], entries["R1/proj/abs.bin"]["unsafe"]) == ("R2/x/big.bin", 0)
    assert totals(entries, "R1/proj") == (2150, 4)

    # the container mounts the same tree elsewhere; the cluster path no longer exists
    mounted = tmp_path / "container-share"
    os.rename(share, mounted)
    settings.share_root = str(mounted)
    _age(mounted, seconds_ago=500)
    _crawl(tasks, settings, NOW + 30 * DAY)

    entries = rows(settings)
    abs_link = entries["R1/proj/abs.bin"]
    assert (abs_link["unsafe"], abs_link["link_target"], abs_link["target_kind"]) == (1, None, "missing")
    assert entries["R1/proj/link.bin"]["link_target"] == "R2/x/big.bin"
    assert entries["R1/proj/link.bin"]["unsafe"] == 0
    assert totals(entries, "R1/proj") == (1150, 3)
