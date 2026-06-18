from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/experiments", tags=["experiments"])


class ExperimentTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, searchable=True, sortable=True),
        TableCol(title="Workflow", label="workflow", col_size=2, choices=C.ExperimentWorkFlow.as_selectable(), sortable=True, sort_by="workflow_id"),
        TableCol(title="Status", label="status", col_size=2, choices=C.ExperimentStatus.as_selectable(), sortable=True, sort_by="status_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Operator", label="operator", col_size=2, searchable=True),
        TableCol(title="Created", label="timestamp_created", col_size=2, sortable=True, sort_by="timestamp_created_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


@router.get("/render-table-page")
async def render_experiment_table(
    project_id: int | None = Query(None, description="Optional project ID to filter experiments"),
    status_in: list[C.ExperimentStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ExperimentStatus, query_param="status_in")),
    workflow_in: list[C.ExperimentWorkFlow] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ExperimentWorkFlow, query_param="workflow_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_insider),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Experiment, default=models.Experiment.id.desc())),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = ExperimentTable(route="render_experiment_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    if workflow_in:
        table.filter_values["workflow"] = workflow_in

    stmt = Q.experiment.select(
        project_id=project_id,
        status_in=status_in,
        workflow_in=workflow_in,
    )

    if project_id is not None:
        template = "components/tables/project-experiment.html"
        table.url_params["project_id"] = project_id
    else:
        template = "components/tables/experiment.html"

    experiments, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Experiment.operator),
            orm.selectinload(models.Experiment.libraries),
            orm.selectinload(models.Experiment.sequencer),
        ]
    )
    table.set_num_pages(count)

    return await responses.htmx_response(template=template, experiments=experiments, table=table)