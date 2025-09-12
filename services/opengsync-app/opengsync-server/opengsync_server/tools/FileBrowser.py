from pathlib import Path
from dataclasses import dataclass

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
        limit: int | None = None, offset: int | None = None
    ) -> list[BrowserPath]:
        if not self._is_safe(subpath):
            return []
        
        full_path = self.root_dir / subpath
        
        if full_path.exists() and full_path.is_dir():
            counter = 0
            paths: list[BrowserPath] = []
            for path in full_path.iterdir():
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