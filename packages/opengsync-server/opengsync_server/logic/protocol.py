import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class ProtocolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Read Structure", label="read_structure", col_size=3),
        TableCol(title="Assay", label="service_type", col_size=2, choices=cats.ServiceType.as_list(), sortable=True, sort_by="service_type_id"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = ProtocolTable(route="protocols_htmx.get", page=request.args.get("page", 0, type=int))

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
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
        if sort_by not in models.Protocol.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (service_type_in := request.args.get("service_type_in")) is not None:
        service_type_in = json.loads(service_type_in)
        try:
            service_type_in = [cats.ServiceType.get(int(service_type)) for service_type in service_type_in]
            if service_type_in:
                fnc_context["service_type_in"] = service_type_in
                table.filter_values["service_type"] = service_type_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    protocols, table.num_pages = db.protocols.find(page=table.active_page, **fnc_context)
    logger.debug(protocols)
        
    context.update({
        "protocols": protocols,
        "template_name_or_list": "components/tables/protocol.html",
        "table": table,
    })
    return context