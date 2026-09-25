from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q


def is_within_root(root_dir: Path, subpath: str | Path) -> bool:
    """True if `root_dir / subpath` resolves inside `root_dir`. Rejects `..` escapes, absolute paths, and symlinks pointing outside."""
    try:
        return (Path(root_dir) / subpath).resolve().is_relative_to(Path(root_dir).resolve())
    except (ValueError, RuntimeError, OSError):
        return False


@dataclass
class BrowserPath:
    path: Path
    rel_path: Path
    data_paths: list[models.DataPath]
    is_dir: bool | None = None
    size: int | None = None
    mtime: float | None = None


class FileBrowser:
    def __init__(self, root_dir: Path, session: SyncSession):
        self.root_dir = Path(root_dir)
        self.session = session

    def list_contents(
        self, subpath: Path = Path(),
        limit: int | None = None, offset: int | None = None,
        sort_by: Literal["name", "size", "mtime"] | None = "name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> list[BrowserPath]:
        if not self._is_safe(subpath):
            return []

        full_path = self.root_dir / subpath

        def sort_by_name(p: Path):
            return p.name.lower()

        def sort_by_size(p: Path):
            try:
                return p.stat().st_size
            except (FileNotFoundError, PermissionError):
                return -1

        def sort_by_mtime(p: Path):
            try:
                return p.stat().st_mtime
            except (FileNotFoundError, PermissionError):
                return -1

        match sort_by:
            case "name":
                key_func = sort_by_name
            case "size":
                key_func = sort_by_size
            case "mtime":
                key_func = sort_by_mtime
            case _:
                key_func = sort_by_name

        if full_path.exists() and full_path.is_dir():
            counter = 0
            paths: list[BrowserPath] = []
            dir_paths = sorted(list(full_path.iterdir()), key=key_func, reverse=(sort_order == "desc"))
            remaining_offset = offset or 0
            for path in dir_paths:
                if remaining_offset:
                    remaining_offset -= 1
                    continue

                if not self._is_safe(path.relative_to(self.root_dir)):
                    continue

                data_paths = self.session.get_all(
                    statement=Q.data_path.select(
                        path=path.relative_to(self.root_dir).as_posix(),
                    ),
                    limit=None,
                    options=[
                        orm.joinedload(models.DataPath.project),
                        orm.joinedload(models.DataPath.seq_request),
                        orm.joinedload(models.DataPath.library),
                        orm.joinedload(models.DataPath.experiment),
                    ],
                )

                paths.append(BrowserPath(
                    path=path,
                    rel_path=path.relative_to(self.root_dir),
                    data_paths=list(data_paths),
                ))

                counter += 1
                if limit is not None and counter >= limit:
                    break
            return paths
        return []

    def _is_safe(self, subpath: Path) -> bool:
        return is_within_root(self.root_dir, subpath)
