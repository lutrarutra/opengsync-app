from pathlib import Path

from dataclasses import dataclass

from opengsync_db import models, DBHandler

@dataclass
class BrowserPath:
    path: Path
    data_paths: list[models.DataPath]


class FileBrowser:
    def __init__(self, root_dir: Path, db: DBHandler):
        self.root_dir = root_dir
        self.db = db

    def list_contents(self, subpath: Path = Path()) -> list[BrowserPath]:
        if not self._is_safe(subpath):
            return []
        
        full_path = self.root_dir / subpath
        
        if full_path.exists() and full_path.is_dir():
            paths: list[BrowserPath] = []
            for path in full_path.iterdir():
                if not self._is_safe(path.relative_to(self.root_dir)):
                    continue
                paths.append(BrowserPath(
                    path=path,
                    data_paths=self.db.data_paths.find(path=path.relative_to(self.root_dir).as_posix(), limit=None)[0]
                ))
            return paths
        return []
    
    def _is_safe(self, subpath: Path) -> bool:
        """Check if the subpath is safe and doesn't escape root_dir"""
        try:
            full_path = (self.root_dir / subpath).resolve()
            return full_path.is_relative_to(self.root_dir)
        except (ValueError, RuntimeError):
            return False