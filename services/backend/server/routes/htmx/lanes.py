from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, exceptions as exc
from ...components.tables import Table, TableState, Col, Text, Exact, Variant, related

router = APIRouter(prefix="/lanes", tags=["lanes"])


LN = models.Lane


class LaneTable(Table):
    key = "lane"
    model = models.Lane
    noun = "lanes"
    load = (orm.selectinload(LN.pool_links), orm.selectinload(LN.experiment))
    default_sort = ("id", "desc")
    columns = [
        Col("id", "ID", sort=True, search=Exact(LN.id), hideable=False, size=1),
        Col(
            "experiment", "Experiment", size=4,
            sort=related(LN.experiment, models.Experiment.name),
            search=Text(models.Experiment.name, via=LN.experiment),
        ),
        Col("lane", "Lane", sort=LN.number, search=Exact(LN.number, prefixes=("L",)), size=2),
        Col("num_pools", "# Pools", size=1),
        Col("qubit_concentration", "Qubit Conc.", size=2),
        Col("avg_fragment_size", "Avg. Fragment Size", size=2),
        Col("molarity", "Molarity", size=2),
        Col("library_volume", "Library Volume", size=2),
        Col("total_volume", "Total Volume", size=2),
    ]
    _browse = dict(row_template="components/tables/rows/browse-lane.html", dom_id="select-lanes-table", url_state=False)
    variants = {
        "default": Variant(
            ["id", "lane", "num_pools", "qubit_concentration", "avg_fragment_size", "molarity", "library_volume", "total_volume"],
            "components/tables/rows/experiment-lane.html", dom_id="experiment-lane-table",
        ),
        "browse": Variant(["experiment", "lane"], **_browse),
        "browse-qubit-measure": Variant(["experiment", "lane", "qubit_concentration"], **_browse),
        "browse-ba-report": Variant(["experiment", "lane", "avg_fragment_size"], **_browse),
    }


@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_lane_table(
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter lanes"),
    browse: str | None = Query(None, description="Optional browse context for lane selection component"),
    state: TableState = Depends(LaneTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    if experiment_id is None and browse is None:
        raise exc.BadRequestException("Experiment or browse context is required to render the lane table.")

    table = LaneTable(state, route="render_lane_table", user=current_user)
    if experiment_id is not None:
        table.use("default", experiment_id=experiment_id, experiment=session.get_one(Q.experiment.select(id=experiment_id)))
    if browse is not None:
        table.use(f"browse-{browse}" if f"browse-{browse}" in LaneTable.variants else "browse", browse=browse)
        table.context["browse_context"] = browse

    return table.render(session, Q.lane.select(experiment_id=experiment_id))
