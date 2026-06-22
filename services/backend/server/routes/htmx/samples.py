import io
import pandas as pd
from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query, Request, Response

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ...core.context import ctx
from ... import forms


router = APIRouter(prefix="/samples", tags=["samples"])


class SampleTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Project", label="project", col_size=2),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=C.SampleStatus.as_selectable()),
        TableCol(title="Owner", label="owner", col_size=1),
        TableCol(title="# Libraries", label="num_libraries", col_size=1),
        TableCol(title="Library Types", label="library_types", col_size=4),
    ]


@router.get("/render-table-page")
async def render_sample_table(
    library_id: int | None = Query(None, description="Optional library ID to filter samples"),
    lab_prep_id: int | None = Query(None, description="Optional lab prep ID to filter samples"),
    project_id: int | None = Query(None, description="Optional project ID to filter samples"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter samples"),
    status_in: list[C.SampleStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.SampleStatus, query_param="status_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Sample, default=models.Sample.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = SampleTable(route="render_sample_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in

    stmt = Q.sample.select(
        library_id=library_id,
        lab_prep_id=lab_prep_id,
        project_id=project_id,
        seq_request_id=seq_request_id,
        status_in=status_in,
    )
    
    if library_id is not None:
        if await session.get_access_level(Q.library.permissions(library_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this library.")
        template = "components/tables/library-sample.html"
        table.url_params["library_id"] = library_id
        table.context["library"] = await session.get_one(Q.library.select(id=library_id))
    elif project_id is not None:
        if await session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this project.")
        template = "components/tables/project-sample.html"
        table.url_params["project_id"] = project_id
        table.context["project"] = await session.get_one(Q.project.select(id=project_id))
    elif seq_request_id is not None:
        if await session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this seq request.")
        template = "components/tables/seq_request-sample.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request"] = await session.get_one(Q.seq_request.select(id=seq_request_id))
    elif lab_prep_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view samples for this lab prep.")
        template = "components/tables/lab_prep-sample.html"
        table.url_params["lab_prep_id"] = lab_prep_id
        table.context["lab_prep"] = await session.get_one(Q.lab_prep.select(id=lab_prep_id))
    else:
        if not current_user.is_insider():
            stmt = Q.sample.select(viewer_id=current_user.id, statement=stmt)
        template = "components/tables/sample.html"

    samples, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Sample.library_links).selectinload(models.links.SampleLibraryLink.library),
            orm.selectinload(models.Sample.owner),
            orm.selectinload(models.Sample.project)
        ]
    )
    table.set_num_pages(count)

    return await responses.htmx_response(template=template, samples=samples, table=table, **table.context)