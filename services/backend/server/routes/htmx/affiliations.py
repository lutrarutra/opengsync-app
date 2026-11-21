from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc
from ...components.tables import Table, TableState, Col, Text, Exact, Enum, Variant, related

router = APIRouter(prefix="/affiliations", tags=["affiliations"])

A = models.links.UserAffiliation
_FULL_NAME = Q.search.full_name(models.User)


class AffiliationTable(Table):
    key = "aff"
    model = models.links.UserAffiliation
    noun = "affiliations"
    default_sort = ("affiliation", "asc")
    load = (orm.selectinload(A.user), orm.selectinload(A.group))
    columns = [
        Col("group_id", "ID", sort=A.group_id, search=Exact(A.group_id), hideable=False, size=1),
        Col("user_id", "ID", sort=A.user_id, search=Exact(A.user_id), hideable=False, size=1),
        Col(
            "group_name", "Group", sort=related(A.group, models.Group.name),
            search=Text(models.Group.name, via=A.group), hideable=False, size=3,
        ),
        Col(
            "user_name", "User", sort=related(A.user, _FULL_NAME),
            search=Text(_FULL_NAME, via=A.user), hideable=False, size=3,
        ),
        Col("email", "Email", sort=related(A.user, models.User.email), search=Text(models.User.email, via=A.user), size=3),
        Col("affiliation", "Affiliation", sort=A.affiliation_type, filter=Enum(C.AffiliationType, column=A.affiliation_type), size=2),
    ]
    variants = {
        "user": Variant(
            ["group_id", "group_name", "affiliation"], "components/tables/rows/user-affiliation.html",
            dom_id="user-affiliation-table", fields=["group_id", "group_name", "affiliation"],
        ),
        "group": Variant(
            ["user_id", "user_name", "email", "affiliation"], "components/tables/rows/group-user.html",
            dom_id="group-user-table", actions=True, fields=["user_id", "user_name", "email", "affiliation"],
        ),
    }

    tie_break = (A.user_id.asc(), A.group_id.asc())  # composite primary key, no id


@router.get("/render-table-page")
def render_affiliation_table(
    user_id: int | None = Query(None, description="Optional user ID to filter affiliations"),
    group_id: int | None = Query(None, description="Optional group ID to filter affiliations"),
    state: TableState = Depends(AffiliationTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session)
):
    stmt = Q.affiliation.select(user_id=user_id, group_id=group_id)
    table = AffiliationTable(state, route="render_affiliation_table", user=current_user, variant="user")

    if user_id is not None:
        if session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("user", user_id=user_id, user=session.get_one(Q.user.select(id=user_id)))
    elif group_id is not None:
        if (access_level := session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("group", group_id=group_id, group=session.get_one(Q.group.select(id=group_id)))
        table.context["access_level"] = access_level
    else:
        raise exc.BadRequestException("Group or User context is required to render affiliation table.")

    return table.render(session, stmt)
