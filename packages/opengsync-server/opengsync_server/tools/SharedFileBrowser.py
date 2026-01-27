import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from opengsync_db import models, DBHandler

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

    def propfind(self, subpath: Path = Path(), depth: int = 0) -> list[DAVResponse]:
        """
        Handle WebDAV PROPFIND request.
        Returns list of DAVResponse objects.
        """
        if not self._is_safe(subpath):
            raise exceptions.NoPermissionsException()

        full_path = self.root_dir / subpath

        if not full_path.exists():
            raise exceptions.NotFoundException(f"File or directory not found: {subpath}")

        # Prepare list of resources to include based on Depth
        resources: list[DAVResponse] = []

        # Always include the requested resource
        target_resource = self._build_resource_props(full_path, subpath, subpath)  # ← requested_subpath = subpath
        if target_resource:
            resources.append(target_resource)

        # If Depth: 1 and it's a directory, include children
        if depth == 1 and full_path.is_dir():
            for child_path in full_path.iterdir():
                child_subpath = child_path.relative_to(self.root_dir)
                if not self._is_safe(child_subpath):
                    continue
                child_resource = self._build_resource_props(child_path, child_subpath, subpath)  # ← requested_subpath = original subpath
                if child_resource:
                    resources.append(child_resource)

        return resources

    def _build_resource_props(self, fs_path: Path, item_subpath: Path, requested_subpath: Path) -> DAVResponse | None:
        """Build DAVResponse for a single file/directory"""
        try:
            stat = fs_path.stat()

            # ✅ FIX: Compute href relative to requested_subpath
            try:
                if requested_subpath in (Path(), Path("/")):
                    # Client requested root
                    rel = item_subpath
                else:
                    # Compute path relative to requested directory
                    rel = item_subpath.relative_to(requested_subpath)
                href = str(rel)
            except ValueError:
                # Fallback (shouldn't happen with _is_safe)
                href = str(item_subpath)

            # Add trailing slash for directories
            if fs_path.is_dir() and not href.endswith('/'):
                href += '/'

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

            propstat = DAVPropStat(
                props=props,
                status_code=200,
                status_text="OK"
            )

            return DAVResponse(
                href=href,
                propstats=[propstat]
            )

        except (OSError, ValueError):
            return None

    def _format_date(self, timestamp: float) -> str:
        """Format timestamp as RFC 1123 (HTTP-Date)"""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    def get_file_info(self, subpath: Path) -> tuple[Path, os.stat_result] | None:
        """Return file path and stat if it's a safe, existing file."""
        if not self._is_safe(subpath):
            return None

        full_path = self.root_dir / subpath

        if full_path.is_file():
            try:
                stat = full_path.stat()
                return full_path, stat
            except OSError:
                return None

        return None