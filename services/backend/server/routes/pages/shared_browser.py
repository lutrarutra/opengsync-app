import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from ...core import config, dependencies, exceptions as exc, responses
from ...utils.file_browser import BrowserPath
from ...utils.io import is_browser_friendly
from ...utils.shared_file_browser import SharedFileBrowser

router = APIRouter(prefix="/files/share/browse", tags=["file-share"])
PAGE_LIMIT = 50


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


def _browser(token: str, session) -> SharedFileBrowser:
    from opengsync_db import models, queries as Q
    from sqlalchemy import orm

    share_token = session.first(
        Q.share_token.select(uuid=token).options(orm.selectinload(models.ShareToken.paths))
    )
    if share_token is None:
        raise exc.NotFoundException("Token Not Found")
    if share_token.is_expired:
        raise exc.NoPermissionsException("Token expired")
    return SharedFileBrowser(Path(config.settings.app_config.share_root), share_token)


def _sort_value(value: str) -> str:
    return value if value in {"name", "size", "mtime"} else "name"


def _order_value(value: str) -> str:
    return value if value in {"asc", "desc"} else "asc"


def _browser_paths(paths: list[Path]) -> list[BrowserPath]:
    root_dir = Path(config.settings.app_config.share_root)
    return [
        BrowserPath(path=path, rel_path=path.relative_to(root_dir), data_paths=[])
        for path in paths
    ]


@router.get("/{token}/entries/{subpath:path}")
def shared_browser_entries(
    token: str,
    subpath: str = "",
    page: int = Query(0, ge=0),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    session=Depends(dependencies.db_session),
):
    current_path = _subpath(subpath)
    browser = _browser(token, session)
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


@router.get("/{token}")
@router.get("/{token}/{subpath:path}")
def shared_browser_page(
    token: str,
    subpath: str = "",
    session=Depends(dependencies.db_session),
):
    current_path = _subpath(subpath)
    browser = _browser(token, session)

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
