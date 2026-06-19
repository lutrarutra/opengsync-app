import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class IndexKitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(title="Index Type", label="type", col_size=2, choices=C.IndexType.as_selectable(), sortable=True, sort_by="type_id"),
        TableCol(title="Protocols", label="protocols", col_size=2),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = IndexKitTable(route="index_kits_htmx.get", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.IndexKit)

    if (name := request.args.get("name")):
        stmt = Q.index_kit.search(name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (identifier := request.args.get("identifier")):
        stmt = Q.index_kit.search(identifier=identifier, statement=stmt)
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.index_kit.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.IndexKit, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.IndexType.get(int(kit_type)) for kit_type in type_in]
            if type_in:
                stmt = Q.index_kit.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    index_kits, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
        
    context.update({
        "index_kits": index_kits,
        "template_name_or_list": "components/tables/index_kit.html",
        "table": table,
    })
    return context


def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)
    stmt = sa.select(models.IndexKit)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.index_kit.search(name=name, statement=stmt)
        else:
            stmt = stmt.order_by(models.IndexKit.name.asc())
    elif (identifier := request.args.get("identifier")) is not None:
        if (identifier := identifier.strip()):
            stmt = Q.index_kit.search(identifier=identifier, statement=stmt)
        else:
            stmt = stmt.order_by(models.IndexKit.identifier.asc())
    elif (identifier_name := request.args.get("identifier_name")) is not None:
        if (identifier_name := identifier_name.strip()):
            stmt = Q.index_kit.search(name=identifier_name, identifier=identifier_name, statement=stmt)
        else:
            stmt = stmt.order_by(models.IndexKit.name.asc())
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")
    
    index_kits, count = db.session.page(stmt, page=page)

    context.update({
        "index_kits": index_kits,
        "template_name_or_list": "components/search/index_kit.html",
    })
    return context