from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/affiliations", tags=["affiliations"])

class AffiliationTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1),
        TableCol(title="User", label="user_name", col_size=3, searchable=True),
        TableCol(title="Group", label="group_name", col_size=3, searchable=True),
        TableCol(title="Email", label="email", col_size=3),
        TableCol(title="Affiliation", label="affiliation", col_size=2, choices=C.AffiliationType.as_selectable(), sortable=True, sort_by="affiliation_type"),
    ]


@router.get("/render-table-page")
def render_affiliation_table(
    user_id: int | None = Query(None, description="Optional user ID to filter affiliations"),
    group_id: int | None = Query(None, description="Optional group ID to filter affiliations"),
    user_name: str | None = Query(None, description="Search by user name"),
    group_name: str | None = Query(None, description="Search by group name"),
    affiliation_in: list[C.AffiliationType] | None = Depends(dependencies.parse_enum_ids(enum_type=C.AffiliationType, query_param="affiliation_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.links.UserAffiliation)),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session)
):
    table = AffiliationTable(route="render_affiliation_table", page=page, order_by=order_by)

    stmt = Q.affiliation.select(
        user_id=user_id,
        group_id=group_id,
        affiliation_type_in=affiliation_in,
    )

    if affiliation_in:
        table.filter_values["affiliation"] = affiliation_in

    if user_name:
        table.active_search_var = "user_name"
        table.active_query_value = user_name
        stmt = Q.affiliation.search(user_name=user_name, statement=stmt)
    elif group_name:
        table.active_search_var = "group_name"
        table.active_query_value = group_name
        stmt = Q.affiliation.search(group_name=group_name, statement=stmt)

    if user_id is not None:
        if (access_level := session.get_access_level(Q.user.permissions(user_id, current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/user-affiliation.html"
        table.url_params["user_id"] = user_id
        table.context["user"] = session.get_one(Q.user.select(id=user_id))
    elif group_id is not None:
        if (access_level := session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/group-user.html"
        table.url_params["group_id"] = group_id
        table.context["access_level"] = access_level
        table.context["group"] = session.get_one(Q.group.select(id=group_id))
    else:
        raise exc.BadRequestException("Group or User context is required to render affiliation table.")

    affiliations = table.paginate(
        session, stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.links.UserAffiliation.user),
            orm.selectinload(models.links.UserAffiliation.group),
        ],
    )
    return table.make_response(affiliations=affiliations)