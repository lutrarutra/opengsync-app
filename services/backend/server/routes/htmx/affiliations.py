from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/affiliations", tags=["affiliations"])

class AffiliationTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1),
        TableCol(title="User", label="user_name", col_size=3, searchable=True),
        TableCol(title="Group", label="group_name", col_size=3, searchable=True),
        TableCol(title="Email", label="email", col_size=3),
        TableCol(title="Affiliation", label="affiliation", col_size=2, choices=C.UserRole.as_selectable(), sortable=True, sort_by="role_id"),
    ]


@router.get("/render-table-page")
def render_affiliation_table(
    user_id: int | None = Query(None, description="Optional user ID to filter affiliations"),
    group_id: int | None = Query(None, description="Optional group ID to filter affiliations"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session)
):
    table = AffiliationTable(route="render_affiliation_table", page=page)

    stmt = Q.affiliation.select(
        user_id=user_id,
        group_id=group_id,
    )

    if user_id is not None:
        if session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/user-affiliation.html"
        table.url_params["user_id"] = user_id
    elif group_id is not None:
        if (access_level := session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/group-user.html"
        table.url_params["group_id"] = group_id
        table.context["access_level"] = access_level
        table.context["group"] = session.get_one(Q.group.select(id=group_id))
    else:
        raise exc.BadRequestException("Group or User context is required to render affiliation table.")

    affiliations, count = session.page(stmt, page=page)
    table.set_num_pages(count)
    return table.make_response(affiliations=affiliations)