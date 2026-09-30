import os
import re
import html
import hashlib
import stat as stat_module
from pathlib import Path
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Iterable, Iterator
from typing import Any, Literal

from opengsync_db import models

from ..core import exceptions as exc
from ..core.redis import RedisClient
from .file_browser import BrowserPath
from .parsing import filter_subpaths
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
        shared_paths: Iterable[str],
        cache_key: str,
        allow_symlink_traversal: bool = True,
        redis: RedisClient | None = None,
    ):
        """`cache_key` must change whenever `shared_paths` does: cached listings and safety checks are stored under it."""
        self.root_dir = root_dir.resolve()
        self.cache_key = cache_key
        self.redis = redis
        self.shared_paths = [(self.root_dir / shared_path).resolve() for shared_path in shared_paths]
        self.ignore = ShareIgnore(self.root_dir)
        # allows relative symlink traversal upstream of shared paths, but not outside of root_dir
        self.allow_symlink_traversal = allow_symlink_traversal

    @classmethod
    def for_share_token(
        cls,
        root_dir: Path,
        share_token: models.ShareToken,
        redis: RedisClient | None = None,
    ) -> "SharedFileBrowser":
        # a token's paths never change, so its uuid is a stable cache key
        return cls(
            root_dir,
            shared_paths=[share_path.path for share_path in share_token.paths],
            cache_key=share_token.uuid,
            redis=redis,
        )

    @classmethod
    def for_project(
        cls,
        root_dir: Path,
        project_id: int,
        data_paths: Iterable[str],
        redis: RedisClient | None = None,
    ) -> "SharedFileBrowser":
        shared_paths = sorted(filter_subpaths(list(data_paths)))
        # adding or removing a data path yields a new key, so the cache never needs invalidating
        digest = hashlib.sha256("\n".join(shared_paths).encode("utf-8")).hexdigest()[:16]
        return cls(
            root_dir,
            shared_paths=shared_paths,
            cache_key=f"project:{project_id}:{digest}",
            redis=redis,
        )

    @staticmethod
    def _sorted_with_stats(
        paths_with_stats: list[tuple[Path, os.stat_result]],
        sort_by: Literal["name", "size", "mtime"],
        sort_order: Literal["asc", "desc"],
    ) -> list[tuple[Path, os.stat_result]]:
        def sort_key(item: tuple[Path, os.stat_result]):
            path, path_stat = item
            if sort_by == "size":
                return path_stat.st_size
            if sort_by == "mtime":
                return path_stat.st_mtime
            return path.name.casefold()

        return sorted(paths_with_stats, key=sort_key, reverse=sort_order == "desc")

    def _to_browser_paths(self, paths_with_stats: list[tuple[Path, os.stat_result]]) -> list[BrowserPath]:
        return [
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

    def list_roots(
        self,
        sort_by: Literal["name", "size", "mtime"] = "name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> list[BrowserPath]:
        """The shared paths themselves, for a top level that skips the directories above them.

        Paths missing from storage are listed last with `exists=False`, so an unmounted share doesn't look like no data.
        """
        cached = share_fs_cache.get_roots(self.redis, self.cache_key, sort_by=sort_by, sort_order=sort_order)
        if cached is not None:
            try:
                return self._paths_from_cache(cached)
            except (KeyError, TypeError, ValueError):
                pass

        paths_with_stats: list[tuple[Path, os.stat_result]] = []
        missing: list[BrowserPath] = []
        for shared_path in self.shared_paths:
            if self._is_junk(shared_path) or not self._is_safe(shared_path):
                continue
            try:
                paths_with_stats.append((shared_path, shared_path.stat()))
            except OSError:
                missing.append(BrowserPath(
                    path=shared_path,
                    rel_path=shared_path.relative_to(self.root_dir),
                    data_paths=[],
                    is_dir=False,
                    size=0,
                    mtime=0,
                    exists=False,
                ))

        result = self._to_browser_paths(self._sorted_with_stats(paths_with_stats, sort_by, sort_order))
        # no size or mtime to sort by, so missing paths follow the name direction
        result.extend(sorted(
            missing,
            key=lambda path: path.rel_path.as_posix().casefold(),
            reverse=sort_by == "name" and sort_order == "desc",
        ))
        share_fs_cache.set_roots(
            self.redis,
            self.cache_key,
            [self._path_to_cache(path) for path in result],
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return result

    def list_contents(
        self,
        subpath: Path = Path(),
        limit: int | None = None,
        offset: int = 0,
        sort_by: Literal["name", "size", "mtime"] = "name",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> list[BrowserPath]:
        # the key pins the shared paths and unsafe subpaths are cached as empty, so a hit needs no safety check
        cached = share_fs_cache.get_listing(
            self.redis,
            self.cache_key,
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
        result: list[BrowserPath] = []

        if self.is_safe(subpath) and full_path.is_dir():
            paths_with_stats: list[tuple[Path, os.stat_result]] = []
            for path in full_path.iterdir():
                if self._is_junk(path) or not self._is_safe(path):
                    continue
                try:
                    paths_with_stats.append((path, path.stat()))
                except OSError:
                    continue

            paths_with_stats = self._sorted_with_stats(paths_with_stats, sort_by, sort_order)
            if offset:
                paths_with_stats = paths_with_stats[offset:]
            if limit is not None:
                paths_with_stats = paths_with_stats[:limit]
            result = self._to_browser_paths(paths_with_stats)

        share_fs_cache.set_listing(
            self.redis,
            self.cache_key,
            [self._path_to_cache(path) for path in result],
            subpath=subpath.as_posix(),
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return result

    def _path_to_cache(self, path: BrowserPath) -> dict[str, Any]:
        return {
            "rel_path": path.rel_path.as_posix(),
            "is_dir": path.is_dir,
            "size": path.size,
            "mtime": path.mtime,
            "exists": path.exists,
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
                exists=item.get("exists", True),
            ))
        return result

    def get_file(self, subpath: Path = Path()) -> Path | None:
        """The file at `subpath` if it is shared. Misses are cached too, so a new file can take `FILE_TTL` to appear.

        A hit is not re-checked against the filesystem; callers serving the file re-check that it still exists.
        """
        if self._is_junk(subpath):
            return None

        full_path = self.root_dir / subpath
        cached = share_fs_cache.get_file(self.redis, self.cache_key, subpath=subpath.as_posix())
        if cached is not None:
            try:
                return full_path if cached["is_file"] else None
            except (KeyError, TypeError):
                pass

        is_file = self.is_safe(subpath) and full_path.is_file()
        share_fs_cache.set_file(self.redis, self.cache_key, {"is_file": is_file}, subpath=subpath.as_posix())
        return full_path if is_file else None

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
        if self._is_junk(subpath):
            raise exc.NotFoundException(f"File or directory not found: {subpath}")

        # only safe subpaths are cached, so a hit needs no safety check
        cached = share_fs_cache.get_propfind(
            self.redis,
            self.cache_key,
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

        if self.ignore.is_ignored(self.root_dir / subpath):
            raise exc.NotFoundException(f"File or directory not found: {subpath}")
        if not self.is_safe(subpath):
            raise exc.NoPermissionsException()

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
            self.cache_key,
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
        if self._is_junk(subpath):
            return iter(())

        # only safe subpaths are cached, so a hit needs no safety check
        cached = share_fs_cache.get_walk(
            self.redis,
            self.cache_key,
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

        if not self.is_safe(subpath):
            return iter(())

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
            self.cache_key,
            [{"rel_path": path.as_posix(), "is_dir": is_dir} for path, is_dir in items],
            subpath=subpath.as_posix(),
        )
        return iter(items)
