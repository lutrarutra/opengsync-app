import io
import pandas as pd
from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query, Request, Response

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol, TextColumn, StaticSpreadsheet
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
def render_sample_table(
    library_id: int | None = Query(None, description="Optional library ID to filter samples"),
    lab_prep_id: int | None = Query(None, description="Optional lab prep ID to filter samples"),
    project_id: int | None = Query(None, description="Optional project ID to filter samples"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter samples"),
    browse: str | None = Query(None, description="Optional browse context to filter samples"),
    name: str | None = Query(None, description="Optional sample name to search samples"),
    status_in: list[C.SampleStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.SampleStatus, query_param="status_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Sample, default=models.Sample.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
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

    if name:
        table.active_search_var = "name"
        table.active_query_value = name

    stmt = Q.sample.search(
        name=name,
        statement=stmt,
    )
    
    if library_id is not None:
        if session.get_access_level(Q.library.permissions(library_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this library.")
        table.template = "components/tables/library-sample.html"
        table.url_params["library_id"] = library_id
        table.context["library"] = session.get_one(Q.library.select(id=library_id))
    elif project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this project.")
        table.template = "components/tables/project-sample.html"
        table.url_params["project_id"] = project_id
        table.context["project"] = session.get_one(Q.project.select(id=project_id))
    elif seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view samples for this seq request.")
        table.template = "components/tables/seq_request-sample.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request"] = session.get_one(Q.seq_request.select(id=seq_request_id))
    elif lab_prep_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view samples for this lab prep.")
        table.template = "components/tables/lab_prep-sample.html"
        table.url_params["lab_prep_id"] = lab_prep_id
        table.context["lab_prep"] = session.get_one(Q.lab_prep.select(id=lab_prep_id))
    elif browse is not None:
        table.template = "components/tables/browse-sample.html"
        table.context["browse_context"] = browse
        table.url_params["browse"] = browse
    else:
        if not current_user.is_insider():
            stmt = Q.sample.select(viewer_id=current_user.id, statement=stmt)
        table.template = "components/tables/sample.html"

    samples, count = session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Sample.library_links).selectinload(models.links.SampleLibraryLink.library),
            orm.selectinload(models.Sample.owner),
            orm.selectinload(models.Sample.project)
        ]
    )
    table.set_num_pages(count)
    return table.make_response(samples=samples)


@router.get("/sample-attribute-spreadsheet")
def render_sample_attribute_spreadsheet(
    project_id: int | None = Query(None, description="Optional project ID to filter samples"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter samples"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):

    if seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        df = session.pd.get_seq_request_sample_table(seq_request_id=seq_request_id)
    elif project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        raise NotImplementedError("Rendering sample attribute spreadsheet for a project is not yet implemented.")
    else:
        raise exc.BadRequestException("Either project_id or seq_request_id must be provided.")

    df["project"] = df["project_identifier"]
    df.loc[df["project"].isna(), "project"] = df.loc[df["project"].isna(), "project_title"]
    df = df.drop(columns=["project_identifier", "project_title", "sample_id"])

    columns: list = [
        TextColumn("sample_name", "Sample Name", width=300),
    ]

    for column in df.columns:
        if column not in {"sample_name", "project"}:
            columns.append(TextColumn(column, column.replace("_", " ").title(), width=200))

    spreadsheet = StaticSpreadsheet(df, columns=columns, )

    return spreadsheet.render()
