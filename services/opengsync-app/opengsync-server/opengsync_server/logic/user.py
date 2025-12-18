import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class UserTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text"),
        TableCol(title="Email", label="email", col_size=3, sortable=True),
        TableCol(title="Role", label="role", col_size=2, choices=cats.UserRole.as_list(), sortable=True, sort_by="role_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    fnc_context = {}
    table = UserTable(route="users_htmx.get", page=request.args.get("page", 0, type=int))

    if (role_in := request.args.get("role_in")):
        role_in = json.loads(role_in)
        try:
            role_in = [cats.UserRole.get(int(role)) for role in role_in]
            if role_in:
                fnc_context["role_in"] = role_in
                table.filter_values["role"] = role_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

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
        if sort_by not in models.User.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
        

    template = "components/tables/user.html"
    if not current_user.is_insider():
        fnc_context["user_id"] = current_user.id

    users, table.num_pages = db.users.find(page=table.active_page, **fnc_context)

    context.update({
        "users": users,
        "template_name_or_list": template,
        "table": table,
    })

    return context

def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    fnc_context = {}
    
    if not (field_name := request.args.get("field_name")):
        raise exceptions.BadRequestException("No search field provided.")
    
    if (selected_id := request.args.get(f"{field_name}-selected")) is not None:
        try:
            selected_id = int(selected_id)
            context["selected_id"] = selected_id
        except ValueError:
            pass
        
    context["field_name"] = field_name
    page = request.args.get("page", 0, type=int)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            fnc_context["name"] = name
        else:
            fnc_context["sort_by"] = "name"
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")
    
    fnc_context["insider"] = request.args.get("insider")

    if (group := context.get("group")) is not None:
        fnc_context["group_id"] = group.id
    else:
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id
    
    users, num_pages = db.users.find(page=page, **fnc_context)

    context.update({
        "users": users,
        "template_name_or_list": "components/search/user.html",
        "num_pages": num_pages,
    })
    return context

