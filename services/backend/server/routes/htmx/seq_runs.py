from fastapi import APIRouter, Depends

from opengsync_db import SyncSession, queries as Q, categories as C, models

from ...core import dependencies
from ... import forms
from ...components.tables import Table, TableState, Col, Text, Exact, Enum, Variant

router = APIRouter(prefix="/seq-runs", tags=["seq-runs"])


SR = models.SeqRun


class SeqRunTable(Table):
    key = "run"
    model = models.SeqRun
    noun = "runs"
    columns = [
        Col("id", "ID", sort=True, search=Exact(SR.id), hideable=False, size=1),
        Col("experiment", "Experiment", sort=SR.experiment_name, search=Text(SR.experiment_name, compact=True), size=2),
        Col("status", "Status", sort=True, filter=Enum(C.RunStatus), size=1),
        Col("cycles", "Cycles", size=1),
        Col("flow_cell_id", "Flow Cell ID", sort=SR.flowcell_id, search=Text(SR.flowcell_id), size=1),
        Col("run_folder", "Run Folder", sort=True, search=Text(SR.run_folder, compact=True), size=4),
        Col("started", "Started", size=2),
        Col("completed", "Completed", size=2),
    ]
    variants = {
        "default": Variant(
            ["id", "experiment", "status", "cycles", "flow_cell_id", "run_folder", "started", "completed"],
            "components/tables/rows/seq_run.html", dom_id="seq_run-table",
        ),
    }


@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_seq_run_table(
    state: TableState = Depends(SeqRunTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = SeqRunTable(state, route="render_seq_run_table", user=current_user)
    return table.render(session, Q.seq_run.select())


router.include_router(forms.models.SeqRunForm.Router())
