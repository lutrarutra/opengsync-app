import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class UserTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True),
        TableCol(title="Email", label="email", col_size=3, sortable=True),
        TableCol(title="Role", label="role", col_size=2, choices=C.UserRole.as_selectable(), sortable=True, sort_by="role_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")

    table = UserTable(route="users_htmx.get", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.User)

    if (role_in := request.args.get("role_in")):
        role_in = json.loads(role_in)
        try:
            role_in = [C.UserRole.get(int(role)) for role in role_in]
            if role_in:
                stmt = Q.user.select(role_in=role_in, statement=stmt)
                table.filter_values["role"] = role_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    if (name := request.args.get("name")):
        stmt = Q.user.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.user.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.User, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
        

    template = "components/tables/user.html"
    if not current_user.is_insider():
        # fnc_context["user_id"] = current_user.id
        stmt = Q.user.select(id=current_user.id, statement=stmt)

    # users, table.num_pages = db.users.find(page=table.active_page, **fnc_context)
    users, count = db.session.page(stmt, page=table.active_page or 0)

    context.update({
        "users": users,
        "template_name_or_list": template,
        "table": table,
    })

    return context

def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)
    stmt = sa.select(models.User)
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            # fnc_context["name"] = name
            stmt = Q.user.select(search_name=name, statement=stmt)
        else:
            # fnc_context["sort_by"] = "name"
            stmt = stmt.order_by(sa.nulls_last(models.User.first_name + ' ' + models.User.last_name.asc()))
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")
    
    if (insider := request.args.get("insider")) is not None:
        if insider.lower() == "true" or isinstance(insider, bool) and insider is True:
            stmt = Q.user.select(insider=True, statement=stmt)
        elif insider.lower() == "false" or isinstance(insider, bool) and insider is False:
            stmt = Q.user.select(insider=False, statement=stmt)
        else:
            raise exceptions.BadRequestException("Invalid value for 'insider' parameter. Must be 'true' or 'false'.")

    if (group := context.get("group")) is not None:
        stmt = Q.user.select(group=group, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.user.select(id=current_user.id, statement=stmt)
    
    # users, num_pages = db.users.find(page=page, **fnc_context)
    users, count = db.session.page(stmt, page=page)

    context.update({
        "users": users,
        "template_name_or_list": "components/search/user.html",
    })
    return context

