from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc
from ... import forms
from ...components.tables import HTMXTable, TableCol


router = APIRouter(prefix="/groups", tags=["groups"])
router.include_router(forms.models.GroupForm.Router())
router.include_router(forms.actions.AddUserToGroupAction.Router())

class GroupTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True),
        TableCol(title="Type", label="type", col_size=2, choices=C.GroupType.as_selectable(), sortable=True, sort_by="type_id"),
        TableCol(title="# Users", label="num_users", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
    ]


@router.get("/render-table-page")
def render_group_table(
    name: str | None = Query(None, description="Search by group name"),
    id: str | None = Query(None, description="Search by group ID"),
    user_id: int | None = Query(None, description="Search by user ID"),
    type_in: list[C.GroupType] | None = Depends(dependencies.parse_enum_ids(C.GroupType, "type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = GroupTable(route="render_group_table", page=page)
    table.template = "components/tables/group.html"
    stmt = Q.group.select(type_in=type_in, user_id=user_id)

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
        stmt = Q.group.search(name=name, statement=stmt)
    elif id:
        table.active_search_var = "id"
        table.active_query_value = str(id)
        try:
            stmt = Q.group.select(id=int("".join(filter(str.isdigit, id))), statement=stmt)
        except ValueError:
            pass

    if user_id is not None:
        if session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            return responses.htmx_response(template="components/tables/group-user.html", groups=[], user_id=user_id)
        table.template = "components/tables/group-user.html"
        table.url_params["user_id"] = user_id
        table.context["user_id"] = user_id
        stmt = Q.group.select(user_id=user_id, statement=stmt)
    if not current_user.is_insider:
        stmt = Q.group.select(user_id=current_user.id, statement=stmt)

    groups, count = session.page(stmt, page=page)
    table.set_num_pages(count)
    return table.make_response(groups=groups)

@router.get("/search")
def search_groups(
    word: str = Query(..., description="Search word for group name"),
    selected_id: int | None = Query(None, description="Currently selected group"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.group.search(name=word)

    if selected_id is not None and not word:
        stmt = Q.group.select(id=selected_id, statement=stmt)

    if not current_user.is_insider:
        stmt = Q.group.select(user_id=current_user.id, statement=stmt)

    groups, count = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/group.html", groups=groups)


@router.delete("/{group_id}/remove-user/{user_id}")
def remove_user_from_group(
    group_id: int,
    user_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to remove users from this group.")

    affiliation = session.get_one(Q.affiliation.select(group_id=group_id, user_id=user_id))
    if affiliation.affiliation_type == C.AffiliationType.OWNER:
        raise exc.NoPermissionsException("You cannot remove an owner from the group.")
    
    session.delete(affiliation)

    return responses.htmx_response(
        redirect=responses.url_for("group_page", group_id=group_id),
        flash=responses.flash("User removed from group.", "success")
    )

@router.post("/{group_id}/make-owner/{user_id}")
def make_owner_of_group(
    group_id: int,
    user_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to make users owners of this group.")

    group = session.get_one(Q.group.select(id=group_id))
    owner_affiliation = session.get_one(Q.affiliation.select(group_id=group_id, user_id=group.owner.id))
    owner_affiliation.affiliation_type = C.AffiliationType.MANAGER
    
    affiliation = session.get_one(Q.affiliation.select(group_id=group_id, user_id=user_id))
    affiliation.affiliation_type = C.AffiliationType.OWNER

    return responses.htmx_response(
        redirect=responses.url_for("group_page", group_id=group_id),
        flash=responses.flash("User is now an owner of the group.", "success")
    )