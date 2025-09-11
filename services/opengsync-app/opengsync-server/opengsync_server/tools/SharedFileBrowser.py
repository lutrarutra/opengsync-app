from pathlib import Path

from opengsync_db import models, DBHandler

from .. import logger


class SharedFileBrowser:
    def __init__(self, root_dir: Path, db: DBHandler, share_token: models.ShareToken):
        self.root_dir = root_dir.resolve()
        self.db = db
        self.share_token = share_token
        self.shared_paths = [(self.root_dir / share_path.path).resolve() for share_path in share_token.paths]

    def list_contents(self, subpath: Path = Path()) -> list[Path]:
        if not self._is_safe(subpath):
            return []
        
        full_path = self.root_dir / subpath
        
        if full_path.exists() and full_path.is_dir():
            paths: list[Path] = []
            for path in full_path.iterdir():
                if not self._is_safe(path.relative_to(self.root_dir)):
                    continue
                paths.append(path)
            return paths

        return []
    
    def get_file(self, subpath: Path = Path()) -> Path | None:
        if not self._is_safe(subpath):
            return None
        
        full_path = self.root_dir / subpath
        
        if full_path.exists() and full_path.is_file():
            return full_path

        return None
        

    def _is_safe(self, subpath: Path) -> bool:
        """Check if the subpath is safe and doesn't escape root_dir"""
        try:
            full_path = (self.root_dir / subpath).resolve()

            if not full_path.is_relative_to(self.root_dir):
                return False
            for shared_path in self.shared_paths:
                if full_path.is_relative_to(shared_path) or shared_path.is_relative_to(full_path):
                    return True
            return False
        except (ValueError, RuntimeError):
            return False