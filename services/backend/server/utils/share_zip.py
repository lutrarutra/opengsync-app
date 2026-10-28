"""File list for downloading a share link as one zip, streamed by nginx's mod_zip (docs/file-share.md).

The app answers with `X-Archive-Files: zip` and one line per entry; mod_zip reads each file from the
internal `/nginx-share/` location, as single downloads do, and streams a stored (uncompressed) zip. Python
never reads file contents.

    - <size> <url-encoded /nginx-share/ location> <name in the zip>     a file, CRC-32 unknown
    0 0 @directory <name in the zip>/                                  a folder

A file is listed only if a single download of it would be served (`SharedFileBrowser.get_file`), and its
real path is re-checked here without any cache: nginx follows symlinks, so this is the last check before
nginx reads the file. Every line is validated again before the list is returned.
"""
import hashlib
import os
import re
import stat as stat_module
from dataclasses import dataclass
from email.utils import formatdate
from pathlib import Path
from urllib.parse import unquote

from loguru import logger

from ..core import config, responses
from .shared_file_browser import SharedFileBrowser

# bump when the list format changes, so old ETags never match
FORMAT_VERSION = 1
LOCATION_PREFIX = "/nginx-share/"
# control characters (each line is one entry; mod_zip splits on line breaks), Unicode line breaks,
# and the characters Windows extractors treat as path separators or drive letters
_UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f\x85\u2028\u2029\\:]")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f\x85\u2028\u2029]")
_LINE = re.compile(r"(?P<crc>-|0) (?P<size>\d+) (?P<location>\S+) (?P<name>.+)")


@dataclass(frozen=True)
class ZipManifest:
    body: str
    # strong: the same files with the same sizes and mtimes give the same zip bytes
    etag: str
    # newest file mtime as an HTTP date, None without files
    last_modified: str | None
    n_files: int
    total_size: int


def is_safe_zip_name(name: str) -> bool:
    """Relative, no `.`/`..`/empty components and nothing an extractor could read as a separator (zip-slip)."""
    name = name.removesuffix("/")
    if not name or name.startswith("/") or _UNSAFE_NAME_CHARS.search(name):
        return False
    return all(part not in ("", ".", "..") for part in name.split("/"))


def is_safe_location(location: str) -> bool:
    """Under `/nginx-share/`, no whitespace (the line is split on spaces) and no `..` once nginx decodes it."""
    if not location.startswith(LOCATION_PREFIX) or any(char.isspace() for char in location):
        return False
    decoded = unquote(location)
    if _CONTROL_CHARS.search(decoded):
        return False
    return all(part not in (".", "..") for part in decoded.split("/"))


def _has_traversal(subpath: Path) -> bool:
    return subpath.is_absolute() or any(part in ("..", ".") for part in subpath.parts)


def _shared_rels(browser: SharedFileBrowser) -> list[Path]:
    """The token's shared paths, share-root relative and sorted; the share root itself is never one."""
    rels = []
    for shared_path in sorted(browser.shared_paths):
        try:
            rel = shared_path.relative_to(browser.root_dir)
        except ValueError:
            continue
        if rel.parts:
            rels.append(rel)
    return rels


def _start_points(browser: SharedFileBrowser, subpath: Path | None) -> list[tuple[Path, str]]:
    """(share-root relative path to walk, its name in the zip). The whole share: every shared path, named by its
    basename, with " (2)", " (3)", … for repeated basenames. A folder: that folder only."""
    if subpath is not None:
        # at or below a shared path: is_safe also accepts the folders above one, which browse needs to navigate
        within_share = any(subpath.is_relative_to(rel) for rel in _shared_rels(browser))
        if _has_traversal(subpath) or not within_share or not browser.is_safe(subpath) or not (browser.root_dir / subpath).is_dir():
            return []
        return [(subpath, subpath.name)]

    starts: list[tuple[Path, str]] = []
    taken: set[str] = set()
    for rel in _shared_rels(browser):
        if not browser.is_safe(rel):
            continue
        name, n = rel.name, 1
        while name in taken:
            n += 1
            name = f"{rel.name} ({n})"
        taken.add(name)
        starts.append((rel, name))
    return starts


def _file_entry(browser: SharedFileBrowser, rel: Path) -> tuple[int, int, str] | None:
    """(size, mtime_ns, location) of a file a single download would serve, None otherwise."""
    if (full_path := browser.get_file(rel)) is None:
        return None
    # uncached: a symlink retargeted outside the share root after the walk or get_file was cached is refused here
    if not Path(os.path.realpath(full_path)).is_relative_to(browser.root_dir):
        logger.warning(f"Share zip: '{rel}' resolves outside the share root, skipped")
        return None
    try:
        st = os.stat(full_path)
    except OSError:
        return None
    if not stat_module.S_ISREG(st.st_mode):
        return None
    location = responses.x_accel_redirect(Path(config.settings.app_config.share_root) / rel)
    if location is None or not is_safe_location(location):
        logger.warning(f"Share zip: '{rel}' has no safe nginx location, skipped")
        return None
    return st.st_size, st.st_mtime_ns, location


def validate_body(body: str) -> None:
    """Re-checks every line of a finished list; raises instead of letting nginx serve a bad entry."""
    for line in body.splitlines():
        if (match := _LINE.fullmatch(line)) is None:
            raise ValueError(f"Malformed zip list line: {line!r}")
        if match["location"] == "@directory":
            if match["crc"] != "0" or match["size"] != "0" or not match["name"].endswith("/"):
                raise ValueError(f"Malformed zip directory line: {line!r}")
        elif match["crc"] != "-" or not is_safe_location(match["location"]):
            raise ValueError(f"Unsafe zip location: {line!r}")
        if not is_safe_zip_name(match["name"]):
            raise ValueError(f"Unsafe name in zip: {line!r}")


def build_manifest(browser: SharedFileBrowser, subpath: Path | None = None) -> ZipManifest | None:
    """The mod_zip file list for the whole share (`subpath` None) or one shared folder; None when there is
    nothing to download or `subpath` is not a shared folder."""
    entries: list[tuple[str, str, int]] = []  # (name, line, mtime_ns)
    for start, prefix in _start_points(browser, subpath):
        for rel, is_dir in browser.walk_contents(start):
            rest = rel.relative_to(start).as_posix()
            name = prefix if rest == "." else f"{prefix}/{rest}"
            if not is_safe_zip_name(name):
                logger.warning(f"Share zip: '{rel}' has a name that is unsafe in a zip, skipped")
                continue
            if is_dir:
                if browser.is_safe(rel):
                    entries.append((f"{name}/", f"0 0 @directory {name}/", 0))
            elif (file := _file_entry(browser, rel)) is not None:
                size, mtime_ns, location = file
                entries.append((name, f"- {size} {location} {name}", mtime_ns))

    files = [(name, line, mtime_ns) for name, line, mtime_ns in entries if not name.endswith("/")]
    if not files:
        return None

    entries.sort(key=lambda entry: entry[0])
    body = "".join(f"{line}\n" for _, line, _ in entries)
    validate_body(body)

    digest = hashlib.sha256(f"v{FORMAT_VERSION}\n".encode())
    for _, line, mtime_ns in entries:
        digest.update(f"{line}\0{mtime_ns}\n".encode())
    newest_ns = max(mtime_ns for _, _, mtime_ns in files)
    return ZipManifest(
        body=body,
        etag=f'"{digest.hexdigest()[:32]}"',
        last_modified=formatdate(newest_ns / 1e9, usegmt=True),
        n_files=len(files),
        total_size=sum(int(line.split(" ", 2)[1]) for _, line, _ in files),
    )
