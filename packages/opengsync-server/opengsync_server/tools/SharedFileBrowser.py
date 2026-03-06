import os
import re
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from opengsync_db import models, DBHandler

from .. import logger
from ..core import exceptions

@dataclass
class DAVProp:
    name: str
    value: str

@dataclass
class DAVPropStat:
    props: list[DAVProp]
    status_code: int
    status_text: str

@dataclass
class DAVResponse:
    href: str
    propstats: list[DAVPropStat]

class SharedFileBrowser:
    OS_JUNK_REGEX = re.compile(
        r'(^|/)'
        r'('
        r'\._'                        # AppleDouble
        r'|\.DS_Store'                # macOS folder config
        r'|Thumbs\.db|desktop\.ini'   # Windows junk
        r'|\.Spotlight-V100|\.Trashes|\.metadata_|\.com\.apple\.timemachine' # macOS indexing/system
        r'|\.hidden'                  # Linux hidden file list
        r'|\.ignored'                 # Common user-level ignore file
        r'|^Network Trash Folder$'    # Old macOS network junk
        r'|^Temporary Items$'         # macOS temp folder
        r')', 
        re.IGNORECASE
    )

    def __init__(self, root_dir: Path, db: DBHandler, share_token: models.ShareToken, allow_symlink_traversal: bool = True):
        self.root_dir = root_dir.resolve()
        self.db = db
        self.share_token = share_token
        self.shared_paths = [(self.root_dir / share_path.path).resolve() for share_path in share_token.paths]
        # allows relative symlink traversal upstream of shared paths, but not outside of root_dir
        self.allow_symlink_traversal = allow_symlink_traversal

    def list_contents(self, subpath: Path = Path()) -> list[Path]:
        if not self.is_safe(subpath):
            return []
        
        full_path = self.root_dir / subpath
        
        if full_path.exists() and full_path.is_dir():
            paths: list[Path] = []
            for path in full_path.iterdir():
                if not self._is_safe(path):
                    continue
                paths.append(path)
            return paths

        return []
    
    def get_file(self, subpath: Path = Path()) -> Path | None:
        if not self.is_safe(subpath):
            return None
        full_path = self.root_dir / subpath
        if full_path.exists() and full_path.is_file():
            return full_path
        return None
        
    def _is_safe(self, full_path: Path) -> bool:
        """Check if the full path is safe and doesn't escape root_dir"""
        try:
            if not full_path.is_relative_to(self.root_dir):
                return False
            if self.allow_symlink_traversal and full_path.is_symlink():
                abs_path = full_path.resolve()
                if not abs_path.is_relative_to(self.root_dir):
                    return False
            for shared_path in self.shared_paths:
                if full_path.is_relative_to(shared_path) or shared_path.is_relative_to(full_path):
                    return True
            return False
        except (ValueError, RuntimeError):
            return False
        
    def is_safe(self, subpath: Path) -> bool:
        """Public method to check if a subpath is safe"""
        try:
            full_path = self.root_dir / subpath
            if not full_path.is_symlink() or not self.allow_symlink_traversal:
                full_path = full_path.resolve()
            return self._is_safe(full_path)
        except (ValueError, RuntimeError, OSError):
            return False

    def propfind(self, subpath: Path = Path(), depth: int = 0) -> list[DAVResponse]:
        """
        Handle WebDAV PROPFIND request.
        Returns list of DAVResponse objects.
        """
        if not self.is_safe(subpath):
            raise exceptions.NoPermissionsException()

        full_path = self.root_dir / subpath

        if not full_path.exists():
            raise exceptions.NotFoundException(f"File or directory not found: {subpath}")

        resources: list[DAVResponse] = []

        target_resource = self._build_resource_props(full_path, subpath)
        if target_resource:
            resources.append(target_resource)

        if depth == 1 and full_path.is_dir():
            for child_path in full_path.iterdir():
                if not self._is_safe(child_path):
                    continue
                child_resource = self._build_resource_props(child_path, subpath)
                if child_resource:
                    resources.append(child_resource)

        return resources

    def _build_resource_props(self, fs_path: Path, requested_subpath: Path) -> DAVResponse | None:
        """Build DAVResponse for a single file/directory"""
        try:
            stat = fs_path.stat()

            try:
                if requested_subpath in (Path(), Path("/")):
                    rel = fs_path.relative_to(self.root_dir)
                else:
                    rel = fs_path.relative_to(self.root_dir / requested_subpath)
                href = rel.as_posix()
            except ValueError:
                href = fs_path.relative_to(self.root_dir).as_posix()

            if fs_path.is_dir() and not href.endswith('/'):
                href += '/'

            href = href.replace("./", "/")

            props = [
                DAVProp("displayname", fs_path.name),
                DAVProp("getlastmodified", self._format_date(stat.st_mtime)),
            ]

            if fs_path.is_file():
                props.append(DAVProp("getcontentlength", str(stat.st_size)))
                props.append(DAVProp("resourcetype", ""))
            elif fs_path.is_dir():
                props.append(DAVProp("resourcetype", "<D:collection/>"))
                props.append(DAVProp("getcontentlength", "0"))

            propstat = DAVPropStat(props=props, status_code=200, status_text="OK")

            return DAVResponse(href=href, propstats=[propstat])

        except (OSError, ValueError):
            return None

    def _format_date(self, timestamp: float) -> str:
        """Format timestamp as RFC 1123 (HTTP-Date)"""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    def get_file_info(self, subpath: Path) -> tuple[Path, os.stat_result] | None:
        """Return file path and stat if it's a safe, existing file."""
        if not self.is_safe(subpath):
            return None

        full_path = self.root_dir / subpath

        if full_path.is_file():
            try:
                stat = full_path.stat()
                return full_path, stat
            except OSError:
                return None

        return None

    def walk_contents(self, subpath: Path = Path()):
        """
        Recursively yield (relative_path, is_dir) for all safe items.
        """
        if not self.is_safe(subpath):
            return

        full_start_path = (self.root_dir / subpath).resolve()
        
        if full_start_path.is_file():
            yield subpath, False
            return

        if not full_start_path.is_dir():
            return

        for root, dirs, files in os.walk(full_start_path):
            root_path = Path(root)
            
            for d in dirs:
                dir_abs = root_path / d
                try:
                    dir_rel = dir_abs.relative_to(self.root_dir)
                    if self._is_safe(dir_abs):
                        yield dir_rel, True
                except ValueError:
                    continue

            for f in files:
                file_abs = root_path / f
                try:
                    file_rel = file_abs.relative_to(self.root_dir)
                    if self._is_safe(file_abs):
                        yield file_rel, False
                except ValueError:
                    continue