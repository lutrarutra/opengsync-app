import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class DilutionTable(HTMXTable):
    columns = [
        TableCol(title="Identifier", label="identifier", col_size=1, sortable=True),
        TableCol(title="Operator", label="operator", col_size=2),
        TableCol(title="Time", label="timestamp_utc", col_size=2),
        TableCol(title="Pool", label="pool_id", col_size=3, sortable=True),
        TableCol(title="Operator", label="operator_id", col_size=3),
        TableCol(title="Qubit Concentration", label="qubit_concentration", col_size=2),
        TableCol(title="Molarity", label="molarity", col_size=2),
        TableCol(title="Volume (uL)", label="volume_ul", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = DilutionTable(route="pools_htmx.get_dilutions", page=None)

    if (path := request.args.get("path")):
        fnc_context["path"] = path
        table.active_search_var = "path"
        table.active_query_value = path
    elif (id_ := request.args.get("id")):
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        sort_by = request.args.get("sort_by", "pool_id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.PoolDilution.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [cats.DataPathType.get(int(t)) for t in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    context = parse_context(current_user, request) | kwargs

    if (pool := context.get("pool")) is not None:
        template = "components/tables/pool-dilution.html"
        fnc_context["pool_id"] = pool.id
        table.url_params["pool_id"] = pool.id
    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-pool-dilution.html"        
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
    else:
        raise exceptions.BadRequestException("No pool or experiment context provided for dilution table.")
    
    dilutions, table.num_pages = db.pools.get_dilutions(page=table.active_page, **fnc_context, limit=None)
    context.update({
        "dilutions": dilutions,
        "template_name_or_list": template,
        "table": table,
    })
    return context