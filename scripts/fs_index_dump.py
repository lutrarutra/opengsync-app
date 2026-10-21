#!/usr/bin/env python3
"""Dump the share roots' file trees for the fs-index, run on the cluster where the filesystem is local.

Writes one gzipped JSON-lines file per root, `<out>/<NAME>.jsonl.gz`, which the app imports into
its SQLite fs-index. Files are written as `<NAME>.jsonl.gz.tmp` and renamed when complete, so an
importer never sees a partial dump.

Line format (one JSON value per line):
    {"kind": "header", ...}                       first line: format version, root, all roots, host, start time
    [path, type, size, mtime]                     one per entry, `type` is "d", "f" or "o" (other)
    [path, "l", size, mtime, target, real, target_type, target_size, target_mtime]
                                                  symlinks; `target` is the raw readlink, `real` the resolved
                                                  absolute path, `target_type` "d", "f", "o", "missing" or "loop"
    {"kind": "ignore", "path": ..., "content": ...}   contents of each `.ngsignore` file
    {"kind": "error", "path": ..., "error": ...}      unreadable directories and entries
    {"kind": "footer", ...}                       last line: entry and error counts, finish time

`path` is relative to the root and POSIX-style; `size` is null for directories; mtimes are integer
seconds. Symlinked directories are recorded but not descended into: their targets are dumped under
their own root, and the importer maps `real` back to a root via the header's `roots`. Undecodable
names are kept as JSON surrogate escapes; decode with `surrogateescape` to get the original bytes.

Usage (all roots, defaults below):
    python3 fs_index_dump.py --out /path/to/fs_index_dumps
Selected roots, or other ones:
    python3 fs_index_dump.py --out DIR --root BSF_SAMPLES_10X
    python3 fs_index_dump.py --out DIR --root NAME=/some/path
As a SLURM job:
    sbatch -c 8 --mem 4G -t 4:00:00 --wrap "python3 fs_index_dump.py --out DIR --threads 8"
"""

import argparse
import errno
import gzip
import json
import os
import queue
import socket
import stat
import sys
import threading
import time
from datetime import datetime, timezone

DEFAULT_ROOTS = {
    "BSF_PROJECTS": "/nobackup/lab_bsf/projects",
    "BSF_SEQUENCES": "/research/lab_bsf/sequences",
    "BSF_SEQUENCES_10X": "/research/lab_bsf/sequences_10x",
    "BSF_SAMPLES": "/nobackup/lab_bsf/samples",
    "BSF_SAMPLES_10X": "/nobackup/lab_bsf/samples_10x",
}

FORMAT = "fs-index-dump"
VERSION = 1
IGNORE_FILENAME = ".ngsignore"
MAX_IGNORE_FILE_SIZE = 1024 * 1024
PROGRESS_INTERVAL_S = 30


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value):
    return json.dumps(value, separators=(",", ":"))


def _type_of(mode):
    if stat.S_ISDIR(mode):
        return "d"
    if stat.S_ISREG(mode):
        return "f"
    return "o"


class RootDumper:
    """Walks one root with a pool of threads; each thread lists a directory and writes its entries as one batch."""

    def __init__(self, name, root, out, threads):
        self.name = name
        self.root = os.path.abspath(root)
        self.out = out
        self.threads = threads
        self.dirs = queue.Queue()
        self.write_lock = threading.Lock()
        self.entries = 0
        self.errors = 0
        self.dirs_done = 0

    def _rel(self, full_path):
        rel = os.path.relpath(full_path, self.root)
        return "" if rel == "." else rel.replace(os.sep, "/")

    def _write(self, lines, entries=0, errors=0, dirs_done=0):
        if not lines and not dirs_done:
            return
        with self.write_lock:
            if lines:
                self.out.write(("\n".join(lines) + "\n").encode("utf-8"))
            self.entries += entries
            self.errors += errors
            self.dirs_done += dirs_done

    def _error(self, path, exc):
        return _dumps({"kind": "error", "path": path, "error": "{}: {}".format(type(exc).__name__, exc)})

    def _symlink_record(self, rel, full, st):
        try:
            target = os.readlink(full)
        except OSError as e:
            target = None
            target_type, target_size, target_mtime, real = "missing", None, None, None
            return [rel, "l", st.st_size, int(st.st_mtime), target, real, target_type, target_size, target_mtime], e

        real = os.path.realpath(full)
        try:
            target_st = os.stat(full)
        except OSError as e:
            target_type = "loop" if e.errno == errno.ELOOP else "missing"
            return [rel, "l", st.st_size, int(st.st_mtime), target, real, target_type, None, None], None

        target_type = _type_of(target_st.st_mode)
        target_size = target_st.st_size if target_type == "f" else None
        return [rel, "l", st.st_size, int(st.st_mtime), target, real, target_type, target_size, int(target_st.st_mtime)], None

    def _read_ignore_file(self, full, st):
        if st.st_size > MAX_IGNORE_FILE_SIZE:
            raise ValueError("ignore file larger than {} bytes".format(MAX_IGNORE_FILE_SIZE))
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _list_dir(self, dir_path):
        lines = []
        entries = errors = 0
        try:
            it = os.scandir(dir_path)
        except OSError as e:
            self._write([self._error(self._rel(dir_path), e)], errors=1, dirs_done=1)
            return

        with it:
            while True:
                try:
                    entry = next(it)
                except StopIteration:
                    break
                except OSError as e:
                    lines.append(self._error(self._rel(dir_path), e))
                    errors += 1
                    break

                full = entry.path
                rel = self._rel(full)
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError as e:
                    # vanished or unreadable between listing and stat
                    lines.append(self._error(rel, e))
                    errors += 1
                    continue

                if stat.S_ISLNK(st.st_mode):
                    record, err = self._symlink_record(rel, full, st)
                    if err is not None:
                        lines.append(self._error(rel, err))
                        errors += 1
                    lines.append(_dumps(record))
                    entries += 1
                    continue

                kind = _type_of(st.st_mode)
                lines.append(_dumps([rel, kind, st.st_size if kind != "d" else None, int(st.st_mtime)]))
                entries += 1

                if kind == "d":
                    self.dirs.put(full)
                elif kind == "f" and entry.name == IGNORE_FILENAME:
                    try:
                        lines.append(_dumps({"kind": "ignore", "path": rel, "content": self._read_ignore_file(full, st)}))
                    except (OSError, ValueError) as e:
                        lines.append(self._error(rel, e))
                        errors += 1

        self._write(lines, entries=entries, errors=errors, dirs_done=1)

    def _worker(self):
        while True:
            dir_path = self.dirs.get()
            if dir_path is None:
                self.dirs.task_done()
                return
            try:
                self._list_dir(dir_path)
            except Exception as e:  # never let one directory kill a worker and hang the join
                self._write([self._error(self._rel(dir_path), e)], errors=1, dirs_done=1)
            finally:
                self.dirs.task_done()

    def _progress(self, stop, started):
        while not stop.wait(PROGRESS_INTERVAL_S):
            elapsed = time.monotonic() - started
            with self.write_lock:
                entries, errors, dirs_done = self.entries, self.errors, self.dirs_done
            print(
                "[{}] {}: {} entries, {} dirs listed, ~{} dirs queued, {} errors, {:.0f} entries/s".format(
                    _now_iso(), self.name, entries, dirs_done, self.dirs.qsize(), errors, entries / max(elapsed, 1e-9),
                ),
                file=sys.stderr, flush=True,
            )

    def run(self):
        started = time.monotonic()
        self.dirs.put(self.root)

        stop = threading.Event()
        progress = threading.Thread(target=self._progress, args=(stop, started), daemon=True)
        progress.start()

        workers = [threading.Thread(target=self._worker, daemon=True) for _ in range(self.threads)]
        for w in workers:
            w.start()
        self.dirs.join()
        for _ in workers:
            self.dirs.put(None)
        for w in workers:
            w.join()

        stop.set()
        return time.monotonic() - started


def dump_root(name, root, roots, out_dir, threads):
    final_path = os.path.join(out_dir, "{}.jsonl.gz".format(name))
    tmp_path = final_path + ".tmp"

    if not os.path.isdir(root):
        print("{}: {} is not a directory, skipping".format(name, root), file=sys.stderr, flush=True)
        return False

    root_st = os.stat(root)
    header = {
        "kind": "header",
        "format": FORMAT,
        "version": VERSION,
        "name": name,
        "root": os.path.abspath(root),
        "root_real": os.path.realpath(root),
        "root_mtime": int(root_st.st_mtime),
        "roots": {k: os.path.abspath(v) for k, v in roots.items()},
        "roots_real": {k: os.path.realpath(v) for k, v in roots.items()},
        "host": socket.gethostname(),
        "started_at": _now_iso(),
    }

    print("[{}] {}: dumping {} with {} threads".format(_now_iso(), name, root, threads), file=sys.stderr, flush=True)
    with gzip.open(tmp_path, "wb", compresslevel=6) as out:
        out.write((_dumps(header) + "\n").encode("utf-8"))
        dumper = RootDumper(name, root, out, threads)
        elapsed = dumper.run()
        footer = {
            "kind": "footer",
            "entries": dumper.entries,
            "dirs_listed": dumper.dirs_done,
            "errors": dumper.errors,
            "finished_at": _now_iso(),
            "elapsed_s": round(elapsed, 1),
        }
        out.write((_dumps(footer) + "\n").encode("utf-8"))

    os.replace(tmp_path, final_path)
    print(
        "[{}] {}: done, {} entries, {} errors in {:.0f}s -> {}".format(
            _now_iso(), name, dumper.entries, dumper.errors, elapsed, final_path,
        ),
        file=sys.stderr, flush=True,
    )
    return True


def parse_roots(values):
    if not values:
        return dict(DEFAULT_ROOTS)
    roots = {}
    for value in values:
        if "=" in value:
            name, path = value.split("=", 1)
        elif value in DEFAULT_ROOTS:
            name, path = value, DEFAULT_ROOTS[value]
        else:
            raise SystemExit("unknown root {!r}: use one of {} or NAME=PATH".format(value, ", ".join(DEFAULT_ROOTS)))
        roots[name] = path
    return roots


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="output directory for <NAME>.jsonl.gz files")
    parser.add_argument(
        "--root", action="append", metavar="NAME[=PATH]",
        help="root to dump (repeatable); a known NAME uses its default path. Default: all known roots",
    )
    parser.add_argument(
        "--threads", type=int, default=4,
        help="directories listed in parallel per root (default 4); keep moderate to spare the metadata server",
    )
    args = parser.parse_args()

    roots = parse_roots(args.root)
    os.makedirs(args.out, exist_ok=True)

    # symlink targets are mapped against all known roots, not just the ones dumped in this run
    all_roots = dict(DEFAULT_ROOTS)
    all_roots.update(roots)

    failed = [name for name, root in roots.items() if not dump_root(name, root, all_roots, args.out, max(1, args.threads))]
    if failed:
        print("failed: {}".format(", ".join(failed)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
