import mimetypes
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from opengsync_db import models

from ...core import config, dependencies, responses
from ...utils.file_browser import BrowserPath
from ...utils.io import is_browser_friendly
from ...core import redis as rds
from ...utils.shared_file_browser import SharedFileBrowser

router = APIRouter(prefix="/files/share/browse", tags=["file-share"])
PAGE_LIMIT = 50


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


def _sort_value(value: str) -> Literal["name", "size", "mtime"]:
    return value if value in {"name", "size", "mtime"} else "name"  # type: ignore[return-value]


def _order_value(value: str) -> Literal["asc", "desc"]:
    return value if value in {"asc", "desc"} else "asc"  # type: ignore[return-value]


def _browser_paths(paths: list[BrowserPath]) -> list[BrowserPath]:
    return paths


@router.get("/{token}/entries", name="shared_browser_entries")
@router.get("/{token}/entries/{subpath:path}", name="shared_browser_entries")
def shared_browser_entries(
    token: str,
    subpath: str = "",
    page: int = Query(0, ge=0),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    share_token: models.ShareToken = Depends(dependencies.load_share_token),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    current_path = _subpath(subpath)
    browser = SharedFileBrowser(
        Path(config.settings.app_config.share_root),
        share_token,
        redis=redis,
    )
    sort_by = _sort_value(sort_by)
    sort_order = _order_value(sort_order)
    paths = browser.list_contents(
        current_path,
        limit=PAGE_LIMIT,
        offset=page * PAGE_LIMIT,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return responses.htmx_response(
        "components/file-browser/entries.html",
        paths=_browser_paths(paths),
        current_path=current_path,
        limit=PAGE_LIMIT,
        current_page=page,
        sort_by=sort_by,
        sort_order=sort_order,
        share_token=token,
    )


@router.get("/{token}", name="shared_browser_page")
@router.get("/{token}/{subpath:path}", name="shared_browser_page_path")
def shared_browser_page(
    token: str,
    subpath: str = "",
    share_token: models.ShareToken = Depends(dependencies.load_share_token),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    current_path = _subpath(subpath)
    browser = SharedFileBrowser(
        Path(config.settings.app_config.share_root),
        share_token,
        redis=redis,
    )

    if not browser.list_contents(current_path):
        if (file := browser.get_file(current_path)) is not None:
            mimetype = mimetypes.guess_type(file)[0] or "application/octet-stream"
            return responses.file_response(
                file,
                filename=file.name,
                content_type=mimetype,
                disposition="inline" if is_browser_friendly(mimetype) else "attachment",
            )

    return responses.html_response(
        "files_page.html",
        current_path=current_path,
        sort_by="name",
        sort_order="asc",
        share_token=token,
        title="Shared Files",
    )
