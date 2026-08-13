import os
import mimetypes

from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm
from loguru import logger
import markdown

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc, config
from ...components.tables import HTMXTable, TableCol, UniverSpreadsheet
from ...forms.models import MediaFileForm
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
    table = MediaFileTable(
        route="render_media_file_table", page=page, order_by=order_by
    )
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

    files, count = session.page(
        stmt,
        page=page,
        order_by=order_by,
        options=[
            orm.selectinload(models.MediaFile.uploader),
        ],
    )
    table.set_num_pages(count)
    return table.make_response(files=files)

@router.get("/seq_auth_form_v2.pdf")
def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"
    path = os.path.join("/static", "resources", "templates", name)
    return responses.file_response(path, filename=name)


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

router.include_router(MediaFileForm.Router())
router.include_router(ShareDirectoryAction.Router())
router.include_router(AssociatePathAction.Router())
