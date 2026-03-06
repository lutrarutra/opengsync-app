from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
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
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    fnc_context = {}
    table = LaneTable(route="lanes_htmx.browse", page=request.args.get("page", 0, type=int))
    table.url_params["workflow"] = kwargs["workflow"]
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = parse_context(current_user, request) | kwargs

    if (name := request.args.get("experiment")):
        fnc_context["experiment_name"] = name
        table.active_search_var = "experiment"
        table.active_query_value = name

    if (experiment := context.get("experiment")):
        fnc_context["experiment_id"] = experiment.id

    elif (id_ := request.args.get("id")):
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Lane.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    lanes, table.num_pages = db.lanes.find(page=table.active_page, **fnc_context)

    context.update({
        "lanes": lanes,
        "template_name_or_list": "components/tables/select-lanes.html",
        "table": table,
    })
    return context