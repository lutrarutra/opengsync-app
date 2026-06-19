import os
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ... import forms

router = APIRouter(prefix="/files", tags=["files"])

class MediaFileTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=5, sortable=True),
        TableCol(title="Extension", label="extension", col_size=1),
        TableCol(title="Type", label="type", col_size=2, choices=C.MediaFileType.as_selectable(), sortable=True, sort_by="type_id"),
        TableCol(title="Uploader", label="uploader", col_size=2, searchable=True),
        TableCol(title="Size", label="size_bytes", col_size=1, sortable=True),
        TableCol(title="Timestamp", label="timestamp_utc", col_size=2, sortable=True),
    ]


@router.get("/render-table-page")
async def render_media_file_table(
    uploader_id: int | None = Query(None, description="Filter files by uploader's user ID."),
    seq_request_id: int | None = Query(None, description="Filter files by sequencing request ID."),
    experiment_id: int | None = Query(None, description="Filter files by experiment ID."),
    lab_prep_id: int | None = Query(None, description="Filter files by lab prep ID."),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.MediaFile, default=models.MediaFile.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = MediaFileTable(route="render_media_file_table", page=page, order_by=order_by)
    stmt = Q.media_file.select(
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
        uploader_id=uploader_id,
    )

    if not current_user.is_insider():
        stmt = Q.media_file.select(viewer_id=current_user.id, statement=stmt)

    files, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.MediaFile.uploader),
        ]
    )
    table.set_num_pages(count)
    return await responses.htmx_response(template="components/tables/media_file.html", files=files, table=table)


@router.get("/upload")
async def render_upload_file_form(
    request: Request,
    seq_request_id: int | None = Query(None),
    experiment_id: int | None = Query(None),
    lab_prep_id: int | None = Query(None),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session),
):
    await forms.models.MediaFileForm.check_permissions(
        session=session,
        current_user=current_user,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
    )

    form = forms.models.MediaFileForm(request, form_type="create")
    return await form.make_response()


@router.post("/upload")
async def upload_file(response = Depends(forms.models.MediaFileForm.upload_file)): return response


@router.get("seq_auth_form_v2.pdf")
async def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"
    path = os.path.join("/static", "resources", "templates", name)
    return await responses.file_response(path, filename=name)

