import os
import re
import html
import stat as stat_module
from pathlib import Path
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Any, Literal

from opengsync_db import models

from ..core import exceptions as exc
from ..core.redis import RedisClient
from .file_browser import BrowserPath
from .share_ignore import ShareIgnore
from . import share_fs_cache


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

    @classmethod
    def _is_junk(cls, path: Path) -> bool:
        return bool(cls.OS_JUNK_REGEX.search(path.name) or cls.OS_JUNK_REGEX.search(path.as_posix()))

    def __init__(
        self,
        root_dir: Path,
        share_token: models.ShareToken,
        allow_symlink_traversal: bool = True,
        redis: RedisClient | None = None,
    ):
        self.root_dir = root_dir.resolve()
        self.share_token = share_token
        self.redis = redis
        self.shared_paths = [(self.root_dir / share_path.path).resolve() for share_path in share_token.paths]
        self.ignore = ShareIgnore(self.root_dir)
        # allows relative symlink traversal upstream of shared paths, but not outside of root_dir
        self.allow_symlink_traversal = allow_symlink_traversal

    def list_contents(
        self,
        subpath: Path = Path(),
        limit: int | None = None,
        offset: int = 0,
        sort_by: Literal["name", "size", "mtime"] = "name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> list[BrowserPath]:
        if not self.is_safe(subpath):
            return []

        cached = share_fs_cache.get_listing(
            self.redis,
            self.share_token.uuid,
            subpath=subpath.as_posix(),
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        if cached is not None:
            try:
                return [path for path in self._paths_from_cache(cached) if not self._is_junk(path.rel_path)]
            except (KeyError, TypeError, ValueError):
                pass

        full_path = self.root_dir / subpath

        if full_path.exists() and full_path.is_dir():
            paths = [
                path for path in full_path.iterdir()
                if not self._is_junk(path) and self._is_safe(path)
            ]

            paths_with_stats: list[tuple[Path, os.stat_result]] = []
            for path in paths:
                try:
                    path_stat = path.stat()
                except OSError:
                    path_stat = None
                if path_stat is not None:
                    paths_with_stats.append((path, path_stat))

            def sort_key(item: tuple[Path, os.stat_result]):
                path, path_stat = item
                if sort_by == "size":
                    return path_stat.st_size
                if sort_by == "mtime":
                    return path_stat.st_mtime
                return path.name.casefold()

            paths_with_stats.sort(key=sort_key, reverse=sort_order == "desc")
            if offset:
                paths_with_stats = paths_with_stats[offset:]
            if limit is not None:
                paths_with_stats = paths_with_stats[:limit]

            result = [
                BrowserPath(
                    path=path,
                    rel_path=path.relative_to(self.root_dir),
                    data_paths=[],
                    is_dir=stat_module.S_ISDIR(path_stat.st_mode),
                    size=path_stat.st_size,
                    mtime=path_stat.st_mtime,
                )
                for path, path_stat in paths_with_stats
            ]
            share_fs_cache.set_listing(
                self.redis,
                self.share_token.uuid,
                [self._path_to_cache(path) for path in result],
                subpath=subpath.as_posix(),
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            return result

        share_fs_cache.set_listing(
            self.redis,
            self.share_token.uuid,
            [],
            subpath=subpath.as_posix(),
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return []

    def _path_to_cache(self, path: BrowserPath) -> dict[str, Any]:
        return {
            "rel_path": path.rel_path.as_posix(),
            "is_dir": path.is_dir,
            "size": path.size,
            "mtime": path.mtime,
        }

    def _paths_from_cache(self, paths: list[dict[str, Any]]) -> list[BrowserPath]:
        result = []
        for item in paths:
            rel_path = Path(item["rel_path"])
            result.append(BrowserPath(
                path=self.root_dir / rel_path,
                rel_path=rel_path,
                data_paths=[],
                is_dir=item["is_dir"],
                size=item["size"],
                mtime=item["mtime"],
            ))
        return result

    def get_file(self, subpath: Path = Path()) -> Path | None:
        if self._is_junk(subpath) or not self.is_safe(subpath):
            return None
        full_path = self.root_dir / subpath
        if full_path.exists() and full_path.is_file():
            return full_path
        return None

    def _is_safe(self, full_path: Path, is_dir: bool | None = None) -> bool:
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
                    return not self.ignore.is_ignored(full_path, is_dir=is_dir)
            return False
        except (ValueError, RuntimeError):
            return False

    def is_safe(self, subpath: Path) -> bool:
        """Public method to check if a subpath is safe"""
        try:
            full_path = self.root_dir / subpath
            if self.ignore.is_ignored(full_path):
                return False
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
        if self._is_junk(subpath) or self.ignore.is_ignored(self.root_dir / subpath):
            raise exc.NotFoundException(f"File or directory not found: {subpath}")
        if not self.is_safe(subpath):
            raise exc.NoPermissionsException()

        cached = share_fs_cache.get_propfind(
            self.redis,
            self.share_token.uuid,
            subpath=subpath.as_posix(),
            depth=depth,
        )
        if cached is not None:
            try:
                return [
                    resource for resource in self._dav_responses_from_cache(cached)
                    if not self._is_junk(Path(urllib.parse.unquote(resource.href.rstrip("/"))))
                ]
            except (KeyError, TypeError, ValueError):
                pass

        full_path = self.root_dir / subpath

        if not full_path.exists():
            raise exc.NotFoundException(f"File or directory not found: {subpath}")

        resources: list[DAVResponse] = []

        target_resource = self._build_resource_props(full_path, subpath)
        if target_resource:
            resources.append(target_resource)

        if depth == 1 and full_path.is_dir():
            for child_path in full_path.iterdir():
                if self._is_junk(child_path) or not self._is_safe(child_path):
                    continue
                child_resource = self._build_resource_props(child_path, subpath)
                if child_resource:
                    resources.append(child_resource)

        share_fs_cache.set_propfind(
            self.redis,
            self.share_token.uuid,
            [self._dav_response_to_cache(resource) for resource in resources],
            subpath=subpath.as_posix(),
            depth=depth,
        )
        return resources

    @staticmethod
    def _dav_response_to_cache(resource: DAVResponse) -> dict[str, Any]:
        return {
            "href": resource.href,
            "propstats": [
                {
                    "props": [
                        {"name": prop.name, "value": prop.value}
                        for prop in propstat.props
                    ],
                    "status_code": propstat.status_code,
                    "status_text": propstat.status_text,
                }
                for propstat in resource.propstats
            ],
        }

    @staticmethod
    def _dav_responses_from_cache(resources: list[dict[str, Any]]) -> list[DAVResponse]:
        return [
            DAVResponse(
                href=resource["href"],
                propstats=[
                    DAVPropStat(
                        props=[DAVProp(name=prop["name"], value=prop["value"]) for prop in propstat["props"]],
                        status_code=propstat["status_code"],
                        status_text=propstat["status_text"],
                    )
                    for propstat in resource["propstats"]
                ],
            )
            for resource in resources
        ]

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
            href = urllib.parse.quote(href, safe="/")

            props = [
                DAVProp("displayname", html.escape(fs_path.name)),
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
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    def get_file_info(self, subpath: Path) -> tuple[Path, os.stat_result] | None:
        """Return file path and stat if it's a safe, existing file."""
        if self._is_junk(subpath) or not self.is_safe(subpath):
            return None

        full_path = self.root_dir / subpath

        if full_path.is_file():
            try:
                stat = full_path.stat()
                return full_path, stat
            except OSError:
                return None

        return None

    def walk_contents(self, subpath: Path = Path()) -> Iterator[tuple[Path, bool]]:
        """
        Recursively yield (relative_path, is_dir) for all safe items.
        """
        if self._is_junk(subpath) or not self.is_safe(subpath):
            return iter(())

        cached = share_fs_cache.get_walk(
            self.redis,
            self.share_token.uuid,
            subpath=subpath.as_posix(),
        )
        if cached is not None:
            try:
                items = [
                    (Path(item["rel_path"]), item["is_dir"])
                    for item in cached
                    if not self._is_junk(Path(item["rel_path"]))
                ]
                return iter(items)
            except (KeyError, TypeError, ValueError):
                pass

        full_start_path = (self.root_dir / subpath).resolve()
        items: list[tuple[Path, bool]] = []

        if full_start_path.is_file():
            items.append((subpath, False))
        elif full_start_path.is_dir():
            for root, dirs, files in os.walk(full_start_path):
                root_path = Path(root)
                # an unsafe directory has no safe descendants, so don't descend into it
                dirs[:] = [
                    d for d in dirs
                    if not self._is_junk(root_path / d) and self._is_safe(root_path / d, is_dir=True)
                ]

                for d in dirs:
                    dir_abs = root_path / d
                    try:
                        items.append((dir_abs.relative_to(self.root_dir), True))
                    except ValueError:
                        continue

                for f in files:
                    file_abs = root_path / f
                    try:
                        file_rel = file_abs.relative_to(self.root_dir)
                        if self._is_junk(file_abs) or not self._is_safe(file_abs, is_dir=False):
                            continue
                        items.append((file_rel, False))
                    except ValueError:
                        continue

        share_fs_cache.set_walk(
            self.redis,
            self.share_token.uuid,
            [{"rel_path": path.as_posix(), "is_dir": is_dir} for path, is_dir in items],
            subpath=subpath.as_posix(),
        )
        return iter(items)
