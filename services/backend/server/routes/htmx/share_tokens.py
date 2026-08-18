from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/share_tokens", tags=["share_tokens"])


class ShareTokenTable(HTMXTable):
    columns = [
        TableCol(title="UUID", label="uuid", col_size=1, searchable=True, sortable=True),
        TableCol(title="Expiration", label="expiration", col_size=4),
        TableCol(title="Time Valid", label="time_valid_min", col_size=4),
        TableCol(title="Owner", label="owner", col_size=4, choices=C.DataPathType.as_selectable(), sortable=True, sort_by="owner_id"),
        TableCol(title="# Paths", label="num_paths", col_size=3, sortable=True),
    ]


@router.get("/render-table-page")
def render_share_token_table(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    project_id: int | None = Query(None, description="Optional project ID to filter share tokens"),
    current_user: models.User = Depends(dependencies.require_insider),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.ShareToken, default=models.ShareToken.uuid.asc())),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = ShareTokenTable(route="render_share_token_table", page=page, order_by=order_by)

    stmt = Q.share_token.select()

    if project_id is not None:
        stmt = Q.share_token.select(project_id=project_id)
        table.url_params["project_id"] = project_id


    share_tokens = table.paginate(
        session, stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.ShareToken.owner),
            orm.selectinload(models.ShareToken.paths),
            orm.with_expression(models.ShareToken._num_paths, models.ShareToken.num_paths.expression),
        ]
    )

    return responses.htmx_response(
        template="components/tables/share_token.html",
        share_tokens=share_tokens,
        table=table,
    )

class DataPathTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Path", label="path", col_size=4, searchable=True, sortable=True),
        TableCol(title="Type", label="type", col_size=2, choices=C.DataPathType.as_selectable(), sortable=True, sort_by="type_id"),
    ]


@router.get("/render-data_path-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_data_path_table(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    library_id: int | None = Query(None, description="Optional library ID to filter data paths"),
    project_id: int | None = Query(None, description="Optional project ID to filter data paths"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter data paths"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter data paths"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.DataPath, default=models.DataPath.path.asc())),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = DataPathTable(route="render_data_path_table", page=page, order_by=order_by)

    stmt = Q.data_path.select(
        library_id=library_id,
        project_id=project_id,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
    )

    if library_id is not None:
        table.template = "components/tables/library-data_path.html"
        table.url_params["library_id"] = library_id
    elif project_id is not None:
        table.template = "components/tables/project-data_path.html"
        table.context["project"] = session.get_one(Q.project.select(id=project_id))
        table.url_params["project_id"] = project_id
    elif seq_request_id is not None:
        table.template = "components/tables/seq_request-data_path.html"
        table.url_params["seq_request_id"] = seq_request_id
    elif experiment_id is not None:
        table.template = "components/tables/experiment-data_path.html"
        table.url_params["experiment_id"] = experiment_id
    else:
        raise exc.BadRequestException("At least one of library_id, project_id, seq_request_id, or experiment_id must be provided")

    data_paths = table.paginate(session, stmt, page=page, order_by=order_by)
    return table.make_response(data_paths=data_paths)