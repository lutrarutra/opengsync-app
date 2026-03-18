import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class FeatureTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(title="Target Name", label="target_name", col_size=2),
        TableCol(title="Target ID", label="target_id", col_size=2),
        TableCol(title="Sequence", label="sequence", col_size=2),
        TableCol(title="Pattern", label="pattern", col_size=2),
        TableCol(title="Read", label="read", col_size=2),
        TableCol(title="Feature Type", label="type", col_size=2, choices=cats.FeatureType.as_selectable(), sortable=True, sort_by="type_id"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:    
    fnc_context = {}
    table = FeatureTable(route="feature_kits_htmx.get_features", page=request.args.get("page", 0, type=int))

    if (name := request.args.get("name")):
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (identifier := request.args.get("identifier")):
        fnc_context["identifier"] = identifier
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            id_ = int("".join(filter(str.isdigit, id_)))
            fnc_context["id"] = id_
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Feature.sortable_fields:
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
    
    if (feature_kit := context.get("feature_kit")):
        template = "components/tables/feature_kit-feature.html"
        fnc_context["feature_kit_id"] = feature_kit.id
        table.url_params["feature_kit_id"] = feature_kit.id
    elif (library := context.get("library")):
        template = "components/tables/library-feature.html"
        fnc_context["library_id"] = library.id
        table.url_params["library_id"] = library.id
    else:
        raise exceptions.BadRequestException("Feature kit context is required to view features")
    
    features, table.num_pages = db.features.find(page=table.active_page, **fnc_context)

    context.update({
        "features": features,
        "template_name_or_list": template,
        "table": table,
    })
    return context