from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class AffiliationTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1),
        TableCol(title="User", label="user_name", col_size=3, searchable=True),
        TableCol(title="Group", label="group_name", col_size=3, searchable=True),
        TableCol(title="Email", label="email", col_size=3),
        TableCol(title="Affiliation", label="affiliation", col_size=2, choices=C.UserRole.as_selectable(), sortable=True, sort_by="role_id"),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = AffiliationTable(route="", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.links.UserAffiliation)
    
    if (user_name := request.args.get("user_name")):
        stmt = Q.affiliation.search(user_name=user_name, statement=stmt)
        table.active_search_var = "user_name"
        table.active_query_value = user_name
    elif (group_name := request.args.get("group_name")):
        stmt = Q.affiliation.search(group_name=group_name, statement=stmt)
        table.active_search_var = "group_name"
        table.active_query_value = group_name
    else:
        sort_by = request.args.get("sort_by", "affiliation_type_id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.links.UserAffiliation, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (group := context.get("group")) is not None:
        template = "components/tables/group-user.html"
        table.route = "groups_htmx.get_affiliations"
        affiliation = db.session.first(Q.affiliation.select(user_id=current_user.id, group_id=group.id))
        stmt = Q.affiliation.select(group_id=group.id, statement=stmt)
        context["can_add_users"] = current_user.is_insider() or affiliation is not None and affiliation.affiliation_type in (C.AffiliationType.OWNER, C.AffiliationType.MANAGER)
        table.url_params["group_id"] = group.id
    elif (user := context.get("user")) is not None:
        template = "components/tables/user-affiliation.html"
        table.route = "users_htmx.get_affiliations"
        table.url_params["user_id"] = user.id
        stmt = Q.affiliation.select(user_id=user.id, statement=stmt)
    else:
        raise exceptions.BadRequestException("Group or User context is required to render group affiliation table.")

    affiliations, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "affiliations": affiliations,
        "group": group,
        "template_name_or_list": template,
        "table": table,
    })

    return context