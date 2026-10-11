"""Read-only access to the application's source code, so the agent can look up how the platform works.

Paths are virtual: the first segment names an allowlisted root (`server/`, `opengsync_db/`, `templates/`, `docs/`).
Everything is resolved and checked against the root, so `..`, absolute paths and symlinks can't escape it.
`docs/` is flat: only its top-level files are exposed, not subfolders such as `docs/plans/` (unimplemented plans).
"""
import time
from functools import cache
from pathlib import Path

import opengsync_db
import regex  # unlike `re`, supports timeouts, so a pathological pattern can't hang a worker thread
from pydantic_ai import ModelRetry

from ...core import templates

ALLOWED_SUFFIXES = {".py", ".html", ".jinja", ".jinja2", ".j2", ".md", ".txt"}
MAX_LIST_ENTRIES = 300
MAX_GREP_RESULTS = 100
MAX_PATTERN_LENGTH = 200
MAX_LINE_LENGTH = 300
MAX_READ_LINES = 400
GREP_TIMEOUT_SECONDS = 5.0

ROOT_DESCRIPTIONS = {
    "server": "FastAPI backend (business logic): routes (pages/htmx/api), forms, workflows, core (auth, config, dependencies)",
    "opengsync_db": "Database layer: SQLAlchemy models, categories (status enums, types), queries",
    "templates": "Jinja2 HTML templates of the web UI",
    "docs": "Explanations of specific features, e.g. file sharing (Markdown)",
}
FLAT_ROOTS = {"docs"}  # roots exposing only their top-level files


@cache
def _roots() -> dict[str, Path]:
    here = Path(__file__).resolve()
    roots = {
        "server": here.parents[2],
        "opengsync_db": Path(opengsync_db.__file__).resolve().parent,
        "templates": Path(templates.j2.env.loader.searchpath[0]).resolve(),  # type: ignore[union-attr]
        "docs": here.parents[5] / "docs",  # repo root (/app in the container)
    }
    return {name: root for name, root in roots.items() if root.is_dir()}


def _is_hidden(root_name: str, rel: Path) -> bool:
    if root_name in FLAT_ROOTS and len(rel.parts) > 1:
        return True
    return any(part.startswith(".") or part == "__pycache__" for part in rel.parts)


def _root_of(real: Path) -> tuple[str, Path]:
    return next((name, root) for name, root in _roots().items() if real.is_relative_to(root))


def _resolve(path: str) -> tuple[Path, str]:
    """Map a virtual path to a real path inside an allowlisted root. Returns (real path, normalised virtual path)."""
    parts = [p for p in path.strip().replace("\\", "/").split("/") if p not in ("", ".")]
    roots = _roots()
    if not parts or parts[0] not in roots:
        raise ModelRetry(f"Path must start with one of: {', '.join(r + '/' for r in roots)} (got {path!r}).")

    root = roots[parts[0]]
    real = root.joinpath(*parts[1:]).resolve()
    if not real.is_relative_to(root):
        raise ModelRetry(f"Path {path!r} is outside the allowed directories.")
    rel = real.relative_to(root)
    if _is_hidden(parts[0], rel) or (parts[0] in FLAT_ROOTS and real.is_dir() and rel.parts):
        raise ModelRetry(f"Path {path!r} is not accessible.")
    if not real.exists():
        raise ModelRetry(f"Path {path!r} does not exist. Use list_dir or grep_code to find files.")
    return real, "/".join([parts[0], *rel.parts])


def _iter_files(real: Path):
    """Source files under `real` (a resolved path inside a root), skipping symlinks that leave the root."""
    if real.is_file():
        if real.suffix in ALLOWED_SUFFIXES:
            yield real
        return
    root_name, root = _root_of(real)
    for file in sorted(real.rglob("*")):
        if (
            file.is_file()
            and file.suffix in ALLOWED_SUFFIXES
            and not _is_hidden(root_name, file.relative_to(root))
            and file.resolve().is_relative_to(root)
        ):
            yield file


def _virtual(file: Path) -> str:
    for name, root in _roots().items():
        if file.is_relative_to(root):
            return "/".join([name, *file.relative_to(root).parts])
    raise ValueError(file)


def list_dir(path: str = "") -> str:
    """List the contents of a source code directory.

    Args:
        path: Directory to list, e.g. `server/routes/htmx`. Leave empty to list the top-level directories.
    """
    if not path.strip():
        return "\n".join(f"{name}/  — {ROOT_DESCRIPTIONS[name]}" for name in _roots())

    real, virtual = _resolve(path)
    if not real.is_dir():
        raise ModelRetry(f"{virtual!r} is a file, use read_file to read it.")

    root_name, root = _root_of(real)
    entries = []
    for child in sorted(real.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
        if (
            _is_hidden(root_name, child.relative_to(root))
            or (root_name in FLAT_ROOTS and child.is_dir())
            or not child.resolve().is_relative_to(root)  # symlink pointing outside the root
        ):
            continue
        if child.is_dir():
            entries.append(child.name + "/")
        elif child.suffix in ALLOWED_SUFFIXES:
            entries.append(child.name)

    if not entries:
        return f"{virtual}/ is empty."
    more = f"\n… {len(entries) - MAX_LIST_ENTRIES} more" if len(entries) > MAX_LIST_ENTRIES else ""
    return f"{virtual}/\n" + "\n".join(entries[:MAX_LIST_ENTRIES]) + more


def grep_code(pattern: str, path: str = "", ignore_case: bool = True, max_results: int = 50) -> str:
    """Search the source code with a regular expression and return matching lines as `path:line: text`.

    Args:
        pattern: Python regular expression, e.g. `class SeqRequestStatus` or `def submit_seq_request`.
        path: Directory or file to search in, e.g. `server/routes`. Leave empty to search everything.
        ignore_case: Whether the search is case-insensitive.
        max_results: Maximum number of matching lines to return (at most 100).
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ModelRetry(f"Pattern is too long (max {MAX_PATTERN_LENGTH} characters).")
    try:
        compiled = regex.compile(pattern, regex.IGNORECASE if ignore_case else 0)
    except regex.error as e:
        raise ModelRetry(f"Invalid regular expression: {e}")

    targets = [_resolve(path)[0]] if path.strip() else list(_roots().values())
    max_results = max(1, min(max_results, MAX_GREP_RESULTS))

    results: list[str] = []
    deadline = time.monotonic() + GREP_TIMEOUT_SECONDS
    for target in targets:
        for file in _iter_files(target):
            try:
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                remaining = deadline - time.monotonic()
                try:
                    if remaining <= 0:
                        raise TimeoutError()
                    matched = compiled.search(line, timeout=remaining)
                except TimeoutError:
                    raise ModelRetry("The search took too long. Use a simpler pattern or narrow the path.")
                if matched:
                    results.append(f"{_virtual(file)}:{lineno}: {line.strip()[:MAX_LINE_LENGTH]}")
                    if len(results) >= max_results:
                        return "\n".join(results) + f"\n… stopped after {max_results} results, narrow the search."
    return "\n".join(results) if results else "No matches."


def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    """Read a source file, returned with line numbers. Reads at most 400 lines per call.

    Args:
        path: File to read, e.g. `opengsync_db/categories/SeqRequestStatus.py`.
        start_line: First line to read (1-based).
        end_line: Last line to read (inclusive). Defaults to start_line + 399.
    """
    real, virtual = _resolve(path)
    if real.is_dir():
        raise ModelRetry(f"{virtual!r} is a directory, use list_dir to list it.")
    if real.suffix not in ALLOWED_SUFFIXES:
        raise ModelRetry(f"{virtual!r} is not a source file.")

    lines = real.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line if end_line is not None else start + MAX_READ_LINES - 1, start + MAX_READ_LINES - 1)
    if start > len(lines):
        raise ModelRetry(f"{virtual!r} has only {len(lines)} lines.")

    body = "\n".join(f"{n:>5}  {lines[n - 1][:MAX_LINE_LENGTH]}" for n in range(start, end + 1))
    more = f"\n… file continues, read from line {end + 1}." if end < len(lines) else ""
    return f"{virtual} (lines {start}-{end} of {len(lines)})\n{body}{more}"


TOOLS = [list_dir, grep_code, read_file]
