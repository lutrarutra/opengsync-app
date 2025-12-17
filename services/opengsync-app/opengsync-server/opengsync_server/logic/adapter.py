from flask import Request

from opengsync_db import models

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class AdapterTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Well", label="well", col_size=3, search_type="text", sortable=True),
        TableCol(title="Name", label="name", col_size=2, sortable=True),
        TableCol(title="Name i7", label="name_i7", col_size=2),
        TableCol(title="Name i5", label="name_i5", col_size=2),
        TableCol(title="Sequence i7", label="sequence_i7", col_size=2),
        TableCol(title="Sequence i5", label="sequence_i5", col_size=2),
        TableCol(title="Sequence 1", label="sequence_1", col_size=2),
        TableCol(title="Sequence 2", label="sequence_2", col_size=2),
        TableCol(title="Sequence 3", label="sequence_3", col_size=2),
        TableCol(title="Sequence 4", label="sequence_4", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    
    fnc_context = {}
    table = AdapterTable(route="adapters_htmx.get", page=request.args.get("page", 0, type=int))

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (well := request.args.get("well")):
        fnc_context["well"] = well
        table.active_search_var = "well"
        table.active_query_value = well
    elif (sequence := request.args.get("sequence")):
        fnc_context["sequence"] = sequence
        table.active_search_var = "sequence"
        table.active_query_value = sequence
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
        if sort_by not in models.Adapter.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    context = parse_context(current_user, request) | kwargs

    if (index_kit := context.get("index_kit")) is not None:
        template = "components/tables/index_kit-adapter.html"  
        table.route = "index_kits_htmx.get_adapters"      
        fnc_context["index_kit_id"] = index_kit.id
        table.url_params["index_kit_id"] = index_kit.id
    else:
        template = "components/tables/adapter.html"

    adapters, table.num_pages = db.adapters.find(page=table.active_page, **fnc_context)
    
    context.update({
        "adapters": adapters,
        "template_name_or_list": template,
        "table": table,
    })
    return context