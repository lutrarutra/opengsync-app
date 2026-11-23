from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc, query_options
from ... import forms
from ...components.tables import Table, TableState, Col, Field, Text, Exact, Enum, Variant


router = APIRouter(prefix="/groups", tags=["groups"])

G = models.Group


class GroupTable(Table):
    key = "grp"
    model = models.Group
    noun = "groups"
    load = (
        orm.with_expression(G._num_users, G.num_users.expression),
        orm.with_expression(G._num_seq_requests, G.num_seq_requests.expression),
        orm.with_expression(G._num_projects, G.num_projects.expression),
    )
    columns = [
        Col("id", "ID", sort=True, search=Exact(G.id), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(G.name), hideable=False, size=5),
        Col("type", "Type", sort=True, filter=Enum(C.GroupType), size=2),
        Col("num_users", "# Users", sort=True, size=1),
        Col("num_projects", "# Projects", sort=True, size=1),
        Col("num_seq_requests", "# Requests", sort=True, size=1),
        Field(
            "member", "Member",
            search=Text(Q.search.full_name(models.User), models.User.email,
                        via=(G.user_links, models.links.UserAffiliation.user), weight=0.9),
        ),
    ]
    variants = {
        "default": Variant(
            ["id", "name", "type", "num_users", "num_seq_requests", "num_projects"], "components/tables/rows/group.html",
            dom_id="group-table",
        ),
    }


@router.get("/render-table-page")
def render_group_table(
    user_id: int | None = Query(None, description="Search by user ID"),
    state: TableState = Depends(GroupTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.group.select(user_id=user_id)
    table = GroupTable(state, route="render_group_table", user=current_user)

    if user_id is not None:
        if session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("default", user_id=user_id)
    if not current_user.is_insider:
        stmt = Q.group.select(user_id=current_user.id, statement=stmt)

    return table.render(session, stmt)


@router.get("/search")
def search_groups(
    word: str | None = Query(None, description="Search word for group name"),
    selected_id: int | None = Query(None, description="Currently selected group"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.group.select()

    if selected_id is not None and not word:
        stmt = Q.group.select(id=selected_id, statement=stmt)
    elif word:
        stmt = Q.group.search(name=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Group.name.asc())

    if not current_user.is_insider:
        stmt = Q.group.select(user_id=current_user.id, statement=stmt)

    return query_options.search_response(session, stmt, page=page, option=query_options.group_option)


@router.delete("/{group_id}/remove-user/{user_id}")
def remove_user_from_group(
    group_id: int,
    user_id: int,
    current_user_id: int = Depends(dependencies.require_user_id),
    session: SyncSession = Depends(dependencies.db_session),
):
    leaving = user_id == current_user_id  # any member may leave a group
    if not leaving and session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user_id)) < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to remove users from this group.")

    affiliation = session.get_one(Q.affiliation.select(group_id=group_id, user_id=user_id))
    if affiliation.affiliation_type == C.AffiliationType.OWNER:
        message = "Transfer the ownership before leaving the group." if leaving else "You cannot remove an owner from the group."
        raise exc.NoPermissionsException(message)
    
    session.delete(affiliation)

    if leaving:
        return responses.htmx_response(
            redirect=responses.url_for("groups_page"), flash=responses.flash("You left the group.", "success"),
        )
    return responses.htmx_response(
        # redirect=responses.url_for("group_page", group_id=group_id),
        flash=responses.flash("User removed from group.", "success")
    )

@router.post("/{group_id}/make-owner/{user_id}")
def make_owner_of_group(
    group_id: int,
    user_id: int,
    current_user_id: int = Depends(dependencies.require_user_id),
    session: SyncSession = Depends(dependencies.db_session),
):
    group = session.get_one(Q.group.select(id=group_id))
    owner = group.owner  # None for a group whose owner affiliation is gone
    # Ownership can only be handed over by the owner (or staff), not taken by a manager.
    if (
        (owner is None or owner.id != current_user_id)
        and session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user_id)) < C.AccessLevel.INSIDER
    ):
        raise exc.NoPermissionsException("Only the group owner can transfer ownership.")

    if (affiliation := session.first(Q.affiliation.select(group_id=group_id, user_id=user_id))) is None:
        raise exc.BadRequestException("User is not a member of this group.")

    if owner is not None and owner.id != user_id:
        owner_affiliation = session.get_one(Q.affiliation.select(group_id=group_id, user_id=owner.id))
        owner_affiliation.affiliation_type = C.AffiliationType.MANAGER

    affiliation.affiliation_type = C.AffiliationType.OWNER

    return responses.htmx_response(
        # redirect=responses.url_for("group_page", group_id=group_id),
        flash=responses.flash("User is now an owner of the group.", "success")
    )

router.include_router(forms.models.GroupForm.Router())
router.include_router(forms.actions.AddUserToGroupAction.Router())