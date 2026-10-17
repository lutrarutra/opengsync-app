from flask import Request
import sqlalchemy as sa

from opengsync_db import models, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class LaneTable(HTMXTable):
    columns = [
        TableCol(title="Experiment", label="experiment", col_size=4),
        TableCol(title="Lane", label="lane", col_size=2),
    ]


def get_browse_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider:
        raise exceptions.NoPermissionsException()
    
    table = LaneTable(route="lanes_htmx.browse", page=request.args.get("page", 0, type=int))
    table.url_params["workflow"] = kwargs["workflow"]
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.Lane)

    if (experiment_name := request.args.get("experiment")):
        stmt = Q.lane.search(experiment_name=experiment_name, statement=stmt)
        table.active_search_var = "experiment"
        table.active_query_value = experiment_name

    if (experiment := context.get("experiment")):
        stmt = Q.lane.select(experiment_id=experiment.id, statement=stmt)

    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.lane.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Lane, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    lanes, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "lanes": lanes,
        "template_name_or_list": "components/tables/select-lanes.html",
        "table": table,
    })
    return context