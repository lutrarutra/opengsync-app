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
import markdown

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc, config
from ...components.tables import HTMXTable, TableCol, UniverSpreadsheet
from ...forms.models import MediaFileForm
from ...utils.file_browser import FileBrowser
from ...utils.io import is_browser_friendly
from ...forms.actions import ShareDirectoryAction, AssociatePathAction

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

router = APIRouter(prefix="/files", tags=["files"])

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
            sort_by="type_id",
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
        if not current_user.is_insider:
            stmt = Q.media_file.select(viewer_id=current_user.id, statement=stmt)

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
    return responses.file_response(path, filename=name)


@router.get("/serve-data-file/{data_path_id}")
def serve_data_file(
    data_path_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_user),
):
    data_path = session.get_one(Q.data_path.select(id=data_path_id))

    if not current_user.is_insider:
        if data_path.project_id is not None:
            if session.get_access_level(Q.project.permissions(data_path.project_id, current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException()
        elif data_path.seq_request_id is not None:
            if session.get_access_level(Q.seq_request.permissions(data_path.seq_request_id, current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException()
        else:
            raise exc.NoPermissionsException()

    path = Path(config.settings.app_config.share_root) / data_path.path
    if not path.exists():
        raise exc.ItemNotFoundException("Data file not found")
    if not path.is_file():
        raise exc.BadRequestException("Data path is not a file")

    mimetype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    disposition = "inline" if is_browser_friendly(mimetype) else "attachment"
    return responses.file_response(path, filename=path.name, content_type=mimetype, disposition=disposition)


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
        raise exc.ItemNotFoundException("File not found on disk.")

    content_type, _ = mimetypes.guess_type(file.name + file.extension)
    if content_type is None:
        content_type = "application/octet-stream"

    renderable = file.extension.lower() in BROWSER_RENDERABLE_EXTENSIONS
    disposition = "inline" if renderable else "attachment"
    filename = f"{file.name}{file.extension}"
    return responses.file_response(filepath, filename, content_type, disposition=disposition)


@router.get("/{media_file_id}/download", dependencies=[Depends(dependencies.media_file_permissions)])
def download_media_file(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    file = session.get_one(Q.media_file.select(id=media_file_id))
    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if not os.path.isfile(filepath):
        raise exc.ItemNotFoundException("File not found on disk.")
    content_type, _ = mimetypes.guess_type(file.name + file.extension)
    if content_type is None:
        content_type = "application/octet-stream"
    disposition = "attachment"
    filename = f"{file.name}{file.extension}"
    return responses.file_response(filepath, filename, content_type, disposition=disposition)


@router.get("/{media_file_id}/xlsx-spreadsheet", dependencies=[Depends(dependencies.media_file_permissions)])
def render_xlsx_spreadsheet(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    file = session.get_one(Q.media_file.select(id=media_file_id))

    filepath = os.path.join(config.settings.app_config.media_folder, file.path)
    if not os.path.isfile(filepath):
        raise exc.ItemNotFoundException("File not found on disk.")

    spreadsheet = UniverSpreadsheet(path=filepath)
    return spreadsheet.make_response()

@router.get("/{media_file_id}/markdown", dependencies=[Depends(dependencies.media_file_permissions)])
def render_markdown_file(
    media_file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    file = session.get_one(Q.media_file.select(id=media_file_id))

    filepath = os.path.join("/media", file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exc.ItemNotFoundException("File not found on disk.")
    
    with open(filepath, "r") as f:
        content = f.read()
    
    return responses.htmx_response(
        content=markdown.markdown(
            content,
            extensions=[
                'tables',
                'pymdownx.tasklist'
            ],
            extension_configs={
                'pymdownx.tasklist': {
                    'custom_checkbox': True,
                    'clickable_checkbox': True
                }
            }
        )
    )

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
    session: SyncSession = Depends(dependencies.db_session),
    _: models.User = Depends(dependencies.require_user),
):
    PAGE_LIMIT = 50
    if sort_order is None:
        sort_order = "asc" if sort_by == "name" else "desc"

    current_path = _subpath(subpath)
    browser = FileBrowser(Path(config.settings.app_config.share_root), session)
    paths = browser.list_contents(
        current_path,
        limit=PAGE_LIMIT,
        offset=page * PAGE_LIMIT,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return responses.htmx_response(
        "components/tables/files-body.html",
        paths=paths,
        current_path=current_path,
        parents_dir=current_path.parent if current_path != Path() else None,
        limit=PAGE_LIMIT,
        current_page=page,
        sort_by=sort_by,
        sort_order=sort_order,
    )


router.include_router(ShareDirectoryAction.Router())
router.include_router(AssociatePathAction.Router())
router.include_router(MediaFileForm.Router())
