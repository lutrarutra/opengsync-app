import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class FeatureKitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, search_type="text", sortable=True),
        TableCol(title="Feature Type", label="type", col_size=2, choices=cats.FeatureType.as_list(), sortable=True, sort_by="type_id"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    
    fnc_context = {}
    table = FeatureKitTable(route="feature_kits_htmx.get", page=request.args.get("page", 0, type=int))

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (identifier := request.args.get("identifier")):
        fnc_context["identifier"] = identifier
        table.active_search_var = "identifier"
        table.active_query_value = identifier
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
        if sort_by not in models.FeatureKit.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [cats.FeatureType.get(int(kit_type)) for kit_type in type_in]
            if type_in:
                fnc_context["type_in"] = type_in
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    feature_kits, table.num_pages = db.feature_kits.find(page=table.active_page, **fnc_context)
        
    context.update({
        "feature_kits": feature_kits,
        "template_name_or_list": "components/tables/feature_kit.html",
        "table": table,
    })
    return context