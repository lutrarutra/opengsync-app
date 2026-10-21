import os
import mimetypes
import asyncio
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import orm
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc, config
from ...core.redis import RedisClient
from ...components.tables import HTMXTable, TableCol, UniverSpreadsheet
from ...forms.models import MediaFileForm
from ...utils.file_browser import (
    FileBrowser, PROJECT_SERVABLE_EXTENSIONS, is_servable, is_within_root, servable_mimetype,
)
from ...utils import fs_index
from ...utils.io import is_browser_friendly, render_markdown
from ...forms.actions import SharePathAction, AssociatePathAction

BROWSER_RENDERABLE_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".html",
    ".htm",
    ".txt",
    ".xml",
    ".json",
    ".webp",
    ".ico",
}

# Renderable files that can carry script. They are served inline under a sandbox CSP so any
# script runs in an opaque origin without access to the viewer's session.
ACTIVE_CONTENT_EXTENSIONS = {".svg", ".html", ".htm", ".xml"}
SANDBOX_HEADERS = {"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"}

router = APIRouter(prefix="/files", tags=["files"])
# Its own prefix: under /files the catch-all browser route would take it, or it would shadow a share folder of that name.
share_files_router = APIRouter(prefix="/share-files", tags=["files"])

# Register form routes before the catch-all browser routes below. Starlette
# matches routes in declaration order, so otherwise GET /upload is consumed by
# /{subpath:path} and renders the file browser instead of the upload form.
router.include_router(MediaFileForm.Router())
router.include_router(SharePathAction.Router())
router.include_router(AssociatePathAction.Router())

_CANARY_TIMEOUT_S = 2.0


def _read_canary(filepath: str) -> tuple[bool, str]:
    try:
        content = Path(filepath).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return False, "File not found or endpoint disconnected"
    except OSError as e:
        return False, f"Error: {e}"
    if content == "ok":
        return True, "online"
    return False, f"File found, but contained: {content!r}"


async def _check_canary(name: str, filepath: str) -> tuple[str, bool, str]:
    try:
        is_ok, msg = await asyncio.wait_for(
            asyncio.to_thread(_read_canary, filepath),
            timeout=_CANARY_TIMEOUT_S,
        )
    except TimeoutError:
        return name, False, "Timeout: Cluster is offline or hanging"
    return name, is_ok, msg


@router.get("/share-status")
async def share_status_check():
    canaries = config.settings.app_config.canary_files
    if not canaries:
        return JSONResponse({"status": "unknown", "details": {}})

    results = await asyncio.gather(*(_check_canary(name, path) for name, path in canaries.items()))
    status_report = {name: msg for name, _, msg in results}
    good_count = sum(is_ok for _, is_ok, _ in results)

    if good_count == len(results):
        status, code = "online", 200
    elif good_count == 0:
        status, code = "offline", 503
    else:
        status, code = "degraded", 503
    return JSONResponse({"status": status, "details": status_report}, status_code=code)


@router.get("/storage-availability")
async def storage_availability_check():
    usage = await asyncio.to_thread(shutil.disk_usage, config.settings.app_config.media_folder)
    return {
        "used": f"{usage.used / (1024**3):.1f} GB",
        "free": f"{usage.free / (1024**3):.1f} GB",
        "total": f"{usage.total / (1024**3):.1f} GB",
        "percent_used": f"{(usage.used / usage.total) * 100:.1f}%",
    }


class MediaFileTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=5, sortable=True),
        TableCol(title="Extension", label="extension", col_size=1),
        TableCol(
            title="Type",
            label="type",
            col_size=2,
            choices=C.MediaFileType.as_selectable(),
            sortable=True,
            sort_by="type",
        ),
        TableCol(title="Uploader", label="uploader", col_size=2, searchable=True),
        TableCol(title="Size", label="size_bytes", col_size=1, sortable=True),
        TableCol(title="Timestamp", label="timestamp_utc", col_size=2, sortable=True),
    ]


@router.get("/render-table-page")
def render_media_file_table(
    uploader_id: int | None = Query(None, description="Filter files by uploader's user ID."),
    seq_request_id: int | None = Query(None, description="Filter files by sequencing request ID."),
    experiment_id: int | None = Query(None, description="Filter files by experiment ID."),
    lab_prep_id: int | None = Query(None, description="Filter files by lab prep ID."),
    type_in: list[C.MediaFileType] | None = Depends(dependencies.parse_enum_ids(enum_type=C.MediaFileType, query_param="type_in")),
    uploader: str | None = Query(None, description="Search by uploader name"),
    id_search: str | None = Query(None, alias="id", description="Search by file ID"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.MediaFile, default=models.MediaFile.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = MediaFileTable(route="render_media_file_table", page=page, order_by=order_by)
    stmt = Q.media_file.select(
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
        uploader_id=uploader_id,
        type_in=type_in,
    )

    if type_in:
        table.filter_values["type"] = type_in

    if uploader:
        table.active_search_var = "uploader"
        table.active_query_value = uploader
        stmt = Q.media_file.search(uploader_name=uploader, statement=stmt)
    elif id_search:
        table.active_search_var = "id"
        table.active_query_value = id_search
        if digits := "".join(filter(str.isdigit, id_search)):
            stmt = Q.media_file.select(id=int(digits), statement=stmt)

    if seq_request_id is not None:
        if (access_level := session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/seq_request-media_file.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request_id"] = seq_request_id
        table.context["access_level"] = access_level
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view files for this experiment.")
        table.template = "components/tables/media_file.html"
        table.url_params["experiment_id"] = experiment_id
        table.context["experiment_id"] = experiment_id
    elif lab_prep_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view files for this lab prep.")
        table.template = "components/tables/media_file.html"
        table.url_params["lab_prep_id"] = lab_prep_id
        table.context["lab_prep_id"] = lab_prep_id
    else:
        raise exc.BadRequestException("Request, experiment or lab prep context is required to render the file table.")

    files = table.paginate(
        session,
        stmt,
        page=page,
        order_by=order_by,
        options=[
            orm.selectinload(models.MediaFile.uploader),
        ],
    )
    return table.make_response(files=files)

@router.get("/seq_auth_form_v2.pdf")
def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"
    path = os.path.join("/static", "resources", "templates", name)
    return responses.file_response(path=path, filename=name)


@router.get("/{media_file_id}/render")
def serve_media_file(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.media_file_permissions),
):
    """Serve a media file. Browser-renderable files are shown inline;
    everything else is sent as a download."""
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    file = session.get_one(Q.media_file.select(id=media_file_id))

    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if not os.path.isfile(filepath):
        raise exc.NotFoundException("File not found on disk.")

    content_type, _ = mimetypes.guess_type(file.name + file.extension)
    if content_type is None:
        content_type = "application/octet-stream"

    renderable = file.extension.lower() in BROWSER_RENDERABLE_EXTENSIONS
    disposition = "inline" if renderable else "attachment"
    filename = f"{file.name}{file.extension}"
    extra_headers = SANDBOX_HEADERS if file.extension.lower() in ACTIVE_CONTENT_EXTENSIONS else None
    return responses.file_response(
        path=filepath, filename=filename, content_type=content_type, disposition=disposition, extra_headers=extra_headers,
    )


@router.get("/{media_file_id}/download", dependencies=[Depends(dependencies.media_file_permissions)])
def download_media_file(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    file = session.get_one(Q.media_file.select(id=media_file_id))
    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if not os.path.isfile(filepath):
        raise exc.NotFoundException("File not found on disk.")
    content_type, _ = mimetypes.guess_type(file.name + file.extension)
    if content_type is None:
        content_type = "application/octet-stream"
    disposition = "attachment"
    filename = f"{file.name}{file.extension}"
    return responses.file_response(path=filepath, filename=filename, content_type=content_type, disposition=disposition)


@router.get("/{media_file_id}/xlsx-spreadsheet", dependencies=[Depends(dependencies.media_file_permissions)])
def render_xlsx_spreadsheet(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    file = session.get_one(Q.media_file.select(id=media_file_id))

    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if not os.path.isfile(filepath):
        raise exc.NotFoundException("File not found on disk.")

    spreadsheet = UniverSpreadsheet(path=filepath)
    return spreadsheet.make_response()

@router.get("/{media_file_id}/markdown", dependencies=[Depends(dependencies.media_file_permissions)])
def render_markdown_file(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    file = session.get_one(Q.media_file.select(id=media_file_id))

    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exc.NotFoundException("File not found on disk.")
    
    with open(filepath, "r") as f:
        content = f.read()
    
    return responses.htmx_response(content=render_markdown(content))

@router.delete("/{media_file_id}/delete")
def delete_media_file(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.media_file_permissions)
):
    file = session.get_one(Q.media_file.select(id=media_file_id))

    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to delete this file.")
    
    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if os.path.isfile(filepath):
        os.remove(filepath)
    session.delete(file)

    return responses.htmx_response(
        flash=responses.flash(f"File {file.name}{file.extension} deleted successfully.", "success"),
    )


# Before the catch-all browser route below, which would otherwise take /search as a subpath.
@router.get("/search", name="file_browser_search")
def file_browser_search(
    q: str = Query("", max_length=512),
    kind: Literal["all", "dirs", "files"] = Query("all"),
    root: str | None = Query(None, max_length=255),
    page: int = Query(0, ge=0),
    pick: bool = Query(False, description="Picking paths to add to a Data tab: only Select on the results"),
    session: SyncSession = Depends(dependencies.db_session),
    fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
    _: models.User = Depends(dependencies.require_insider),
):
    """Searches the fs-index; folders expand into the live browser."""
    entries, has_more, error, roots = [], False, None, []
    if fs_index_session is None:
        error = "unavailable"
    else:
        roots = fs_index.roots(fs_index_session)
        try:
            entries, has_more = fs_index.search_page(fs_index_session, q, page=page, kind=kind, root=root)
        except fs_index.QueryTooShort:
            error = "too_short"

    return responses.htmx_response(
        template="components/file-browser/search-results.html",
        results=fs_index.to_results(entries, q, session),
        query=q,
        kind=kind,
        root=root,
        roots=roots,
        page=page,
        has_more=has_more,
        error=error,
        min_term_length=fs_index.MIN_TERM_LENGTH,
        indexed_at=fs_index.indexed_at(fs_index_session),
        search_route="file_browser_search",
        entries_route="render_file_browser_page",
        route_params={"pick": 1} if pick else {},
        insider_actions=True,
        picker=pick,
        file_route=None if pick else "serve_share_file",
        servable_extensions=PROJECT_SERVABLE_EXTENSIONS,
    )


@router.get("/index-status", name="fs_index_status")
def fs_index_status(
    fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
    redis: RedisClient = Depends(dependencies.redis),
    _: models.User = Depends(dependencies.require_insider),
):
    """fs-index summary for the insider dashboard's System tab."""
    return responses.htmx_response(
        template="components/fs-index-status.html",
        # not `status`: that is htmx_response's HTTP status code
        index=fs_index.index_status(fs_index_session, redis),
        enabled=config.settings.app_config.fs_index.enabled,
    )


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


@router.get("/")
@router.get("/{subpath:path}")
def render_file_browser_page(
    subpath: str = "",
    page: int = Query(0, ge=0),
    sort_by: Literal["name", "size", "mtime"] = Query("name"),
    sort_order: Literal["asc", "desc"] | None = Query(None),
    located: bool = Query(False, description="Opened as the current location: render a path bar above the entries"),
    pick: bool = Query(False, description="Picking paths to add to a Data tab: only Select on the entries"),
    session: SyncSession = Depends(dependencies.db_session),
    redis: RedisClient = Depends(dependencies.redis),
    _: models.User = Depends(dependencies.require_insider),
):
    PAGE_LIMIT = 50
    if sort_order is None:
        sort_order = "asc" if sort_by == "name" else "desc"

    current_path = _subpath(subpath)
    share_root = Path(config.settings.app_config.share_root)
    browser = FileBrowser(share_root, session)
    paths = browser.list_contents(
        current_path,
        limit=PAGE_LIMIT,
        offset=page * PAGE_LIMIT,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    # e.g. a stale search result: say so instead of showing an empty folder
    missing = (
        page == 0 and bool(current_path.parts) and is_within_root(share_root, current_path)
        and not (share_root / current_path).is_dir()
    )
    if page == 0:
        # a missing folder too: the crawler then drops it from the index
        fs_index.touch(redis, current_path)

    return responses.htmx_response(
        template="components/file-browser/entries.html",
        paths=paths,
        current_path=current_path,
        limit=PAGE_LIMIT,
        current_page=page,
        sort_by=sort_by,
        sort_order=sort_order,
        share_token=None,
        route_params={"pick": 1} if pick else {},
        picker=pick,
        file_route=None if pick else "serve_share_file",
        servable_extensions=PROJECT_SERVABLE_EXTENSIONS,
        location_header=located and page == 0,
        missing=missing,
    )


@share_files_router.get("/{subpath:path}", name="serve_share_file")
def serve_share_file(
    subpath: str,
    _: models.User = Depends(dependencies.require_insider),
):
    """Opens a file from the insider browser, like the Data tab's serve_<entity>_file but over the whole share.
    The URL mirrors the share root, so relative links in HTML reports resolve."""
    share_root = Path(config.settings.app_config.share_root)
    rel_path = _subpath(subpath)
    path = share_root / rel_path
    if not rel_path.parts or not is_within_root(share_root, rel_path) or not path.is_file():
        raise exc.NotFoundException("File not found. It may have been moved or deleted recently.")
    if not is_servable(path):
        raise exc.NoPermissionsException("This file can't be opened in the browser, only downloaded through a data share link.")

    mimetype = servable_mimetype(path)
    return responses.file_response(
        path=path,
        filename=path.name,
        content_type=mimetype,
        disposition="inline" if is_browser_friendly(mimetype) else "attachment",
        require_accel=True,
    )
