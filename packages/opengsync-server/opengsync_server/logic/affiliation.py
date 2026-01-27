import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class AffiliationTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1),
        TableCol(title="User", label="user_name", col_size=3, search_type="text"),
        TableCol(title="Group", label="group_name", col_size=3, search_type="text"),
        TableCol(title="Email", label="email", col_size=3),
        TableCol(title="Affiliation", label="affiliation", col_size=2, choices=cats.UserRole.as_list(), sortable=True, sort_by="role_id"),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = AffiliationTable(route="", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    
    if (user_name := request.args.get("user_name")):
        fnc_context["user_name"] = user_name
        table.active_search_var = "user_name"
        table.active_query_value = user_name
    elif (group_name := request.args.get("group_name")):
        fnc_context["group_name"] = group_name
        table.active_search_var = "group_name"
        table.active_query_value = group_name
    elif (id_ := request.args.get("id")):
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        sort_by = request.args.get("sort_by", "affiliation_type_id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.links.UserAffiliation.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (group := context.get("group")) is not None:
        template = "components/tables/group-user.html"
        table.route = "groups_htmx.get_affiliations"
        affiliation = db.groups.get_user_affiliation(current_user.id, group.id)
        context["can_add_users"] = current_user.is_insider() or affiliation is not None and affiliation.affiliation_type in (cats.AffiliationType.OWNER, cats.AffiliationType.MANAGER)
        table.url_params["group_id"] = group.id
        affiliations, table.num_pages = db.groups.get_affiliations(group_id=group.id, page=table.active_page, **fnc_context)
    elif (user := context.get("user")) is not None:
        template = "components/tables/user-affiliation.html"
        table.route = "users_htmx.get_affiliations"
        table.url_params["user_id"] = user.id
        affiliations, table.num_pages = db.users.get_affiliations(user_id=user.id, page=table.active_page, **fnc_context)
    else:
        raise exceptions.BadRequestException("Group or User context is required to render group affiliation table.")

    context.update({
        "affiliations": affiliations,
        "group": group,
        "template_name_or_list": template,
        "table": table,
    })

    return context