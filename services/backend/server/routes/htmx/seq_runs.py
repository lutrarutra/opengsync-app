from fastapi import APIRouter, Depends, Query

from opengsync_db import SyncSession, queries as Q, categories as C, utils, models

from ...core import dependencies
from ... import forms
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/seq-runs", tags=["seq-runs"])


class SeqRunTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Experiment", label="experiment", col_size=2, searchable=True, sortable=True, sort_by="experiment_name"),
        TableCol(title="Status", label="status", col_size=1, choices=C.RunStatus.as_selectable(), sortable=True, sort_by="status_id"),
        TableCol(title="Cycles", label="cycles", col_size=1),
        TableCol(title="Flow Cell ID", label="flow_cell_id", searchable=True, col_size=1),
        TableCol(title="Run Folder", label="run_folder", col_size=4, searchable=True),
        TableCol(title="Started", label="started", col_size=2),
        TableCol(title="Completed", label="completed", col_size=2),
    ]


@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_seq_run_table(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    status_in: list[C.RunStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.RunStatus, query_param="status_in")),
    experiment: str | None = Query(None, description="Search by experiment name"),
    run_folder: str | None = Query(None, description="Search by run folder"),
    flow_cell_id: str | None = Query(None, description="Search by flow cell ID"),
    id_search: str | None = Query(None, alias="id", description="Search by run ID"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.SeqRun, default=models.SeqRun.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = SeqRunTable(route="render_seq_run_table", page=page, order_by=order_by)
    table.template = "components/tables/seq_run.html"

    stmt = Q.seq_run.select(status_in=status_in)
    if status_in:
        table.filter_values["status"] = status_in

    if experiment:
        table.active_search_var = "experiment"
        table.active_query_value = experiment
        stmt = Q.seq_run.search(experiment_name=experiment, statement=stmt)
    elif run_folder:
        table.active_search_var = "run_folder"
        table.active_query_value = run_folder
        stmt = Q.seq_run.search(run_folder=run_folder, statement=stmt)
    elif flow_cell_id:
        table.active_search_var = "flow_cell_id"
        table.active_query_value = flow_cell_id
        stmt = Q.seq_run.search(flow_cell_id=flow_cell_id, statement=stmt)
    elif id_search:
        table.active_search_var = "id"
        table.active_query_value = id_search
        digits = "".join(filter(str.isdigit, id_search))
        if digits:
            stmt = Q.seq_run.select(id=int(digits), statement=stmt)

    seq_runs, count = session.page(stmt, page=page, order_by=order_by)
    table.set_num_pages(count)
    return table.make_response(seq_runs=seq_runs)


router.include_router(forms.models.SeqRunForm.Router())
