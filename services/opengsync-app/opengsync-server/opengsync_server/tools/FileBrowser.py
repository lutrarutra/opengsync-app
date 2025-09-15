from pathlib import Path
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import orm

from opengsync_db import models, DBHandler

@dataclass
class BrowserPath:
    path: Path
    rel_path: Path
    data_paths: list[models.DataPath]


class FileBrowser:
    def __init__(self, root_dir: Path, db: DBHandler):
        self.root_dir = root_dir
        self.db = db

    def list_contents(
        self, subpath: Path = Path(),
        limit: int | None = None, offset: int | None = None,
        sort_by: Literal["name", "size", "mtime"] | None = "name",
        sort_order: Literal["asc", "desc"] = "asc"
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
            for path in dir_paths:
                if offset:
                    offset -= 1
                    continue
                
                if not self._is_safe(path.relative_to(self.root_dir)):
                    continue
                
                paths.append(BrowserPath(
                    path=path,
                    rel_path=path.relative_to(self.root_dir),
                    data_paths=self.db.data_paths.find(
                        path=path.relative_to(self.root_dir).as_posix(), limit=None,
                        options=[
                            orm.joinedload(models.DataPath.project),
                            orm.joinedload(models.DataPath.seq_request),
                            orm.joinedload(models.DataPath.library),
                            orm.joinedload(models.DataPath.experiment),
                        ]  # type: ignore
                    )[0]
                ))

                counter += 1
                if limit is not None and counter >= limit:
                    break
            return paths
        return []
    
    def _is_safe(self, subpath: Path) -> bool:
        """Check if the subpath is safe and doesn't escape root_dir"""
        try:
            full_path = (self.root_dir / subpath).resolve()
            return full_path.is_relative_to(self.root_dir)
        except (ValueError, RuntimeError):
            return False