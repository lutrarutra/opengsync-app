import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

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
        TableCol(title="Feature Type", label="type", col_size=2, choices=C.FeatureType.as_selectable(), sortable=True, sort_by="type_id"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:    
    table = FeatureTable(route="feature_kits_htmx.get_features", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.Feature)

    if (name := request.args.get("name")):
        stmt = Q.feature.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (identifier := request.args.get("identifier")):
        stmt = Q.feature.select(search_identifier=identifier, statement=stmt)
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.feature.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Feature, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
        
    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.FeatureType.get(int(kit_type)) for kit_type in type_in]
            if type_in:
                stmt = Q.feature.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    context = parse_context(current_user, request) | kwargs
    
    if (feature_kit := context.get("feature_kit")):
        template = "components/tables/feature_kit-feature.html"
        stmt = Q.feature.select(feature_kit_id=feature_kit.id, statement=stmt)
        table.url_params["feature_kit_id"] = feature_kit.id
    elif (library := context.get("library")):
        template = "components/tables/library-feature.html"
        stmt = Q.feature.select(library_id=library.id, statement=stmt)
        table.url_params["library_id"] = library.id
    else:
        raise exceptions.BadRequestException("Feature kit context is required to view features")
    
    features, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "features": features,
        "template_name_or_list": template,
        "table": table,
    })
    return context