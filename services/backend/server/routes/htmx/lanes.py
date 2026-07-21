from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils, units, actions

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ...components.tables import StaticSpreadsheet, TextColumn
from ... import forms

router = APIRouter(prefix="/lanes", tags=["lanes"])


class LaneTable(HTMXTable):
    columns = [
        TableCol(title="Experiment", label="experiment", col_size=4),
        TableCol(title="Lane", label="lane", col_size=2),
    ]

@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_lane_table(
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter lanes"),
    experiment: str | None = Query(None, description="Optional experiment name to search lanes"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    browse: str | None = Query(None, description="Optional browse context for lane selection component"),
    order_by: utils.OrderBy | None = Depends(
        dependencies.parse_order_by(
            model=models.Lane,
            default=models.Lane.id.desc(),
        )
    ),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = LaneTable(route="render_lane_table", page=page, order_by=order_by)

    stmt = Q.lane.select(
        experiment_id=experiment_id,
    )

    if experiment:
        table.active_search_var = "experiment"
        table.active_query_value = experiment
        stmt = Q.lane.search(experiment_name=experiment, statement=stmt)

    if experiment_id is not None:
        table.template = "components/tables/experiment-lane.html"
        table.url_params["experiment_id"] = experiment_id
        table.context["experiment"] = session.get_one(Q.experiment.select(id=experiment_id))

    if browse is not None:
        table.template = "components/tables/browse-lane.html"
        table.context["browse_context"] = browse
        table.url_params["browse"] = browse

    lanes, count = session.page(stmt, page=page, order_by=order_by)
    table.set_num_pages(count)
    return table.make_response(lanes=lanes)