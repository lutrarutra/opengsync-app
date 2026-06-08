import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class GroupTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True),
        TableCol(title="Type", label="type", col_size=2, choices=C.GroupType.as_selectable(), sortable=True, sort_by="type_id"),
        TableCol(title="# Users", label="num_users", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = GroupTable(route="groups_htmx.get", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.Group)

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.GroupType.get(int(role)) for role in type_in]
            if type_in:
                stmt = Q.group.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        # fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.group.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Group, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if not current_user.is_insider():
        stmt = Q.group.select(user=current_user, statement=stmt)

    groups, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context = parse_context(current_user, request) | kwargs
    context.update({
        "groups": groups,
        "template_name_or_list": "components/tables/group.html",
        "table": table,
    })
    return context


def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)
    stmt = sa.select(models.Group)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.group.select(search_name=name, statement=stmt)
        else:
            stmt = stmt.order_by(models.Group.name.desc())
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")

    if not current_user.is_insider():
        stmt = Q.group.select(user=current_user, statement=stmt)
    
    groups, count = db.session.page(stmt, page=page)

    context.update({
        "groups": groups,
        "template_name_or_list": "components/search/group.html",
    })
    return context