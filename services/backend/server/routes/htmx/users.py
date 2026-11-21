from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, query_options
from ...components.tables import Table, TableState, Col, Field, Text, Exact, Enum, Entity, Variant
from ... import forms


router = APIRouter(prefix="/users", tags=["users"])

U = models.User
_FULL_NAME = Q.search.full_name(models.User)
_GROUP_PATH = (U.affiliations, models.links.UserAffiliation.group)


class UserTable(Table):
    key = "user"
    model = models.User
    noun = "users"
    load = (
        orm.with_expression(U._num_seq_requests, U.num_seq_requests.expression),
        orm.with_expression(U._num_projects, U.num_projects.expression),
    )
    columns = [
        Col("id", "ID", sort=True, search=Exact(U.id), hideable=False, size=1),
        Col("name", "Name", sort=_FULL_NAME, search=Text(_FULL_NAME), hideable=False, size=3),
        Col("email", "Email", sort=True, search=Text(U.email), size=3),
        Col("role", "Role", sort=True, filter=Enum(C.UserRole), size=2),
        Col("num_seq_requests", "# Seq Requests", sort=True, size=1),
        Col("num_projects", "# Projects", sort=True, size=1),
        Field(
            "group", "Group",
            search=Text(models.Group.name, via=_GROUP_PATH),
            filter=Entity(models.Group, via=_GROUP_PATH, option=query_options.group_option, search=(models.Group.name,)),
        ),
    ]
    variants = {
        "default": Variant(
            ["id", "name", "email", "role", "num_seq_requests", "num_projects"], "components/tables/rows/user.html",
            dom_id="user-table", actions=True,
        ),
    }


@router.get("/render-table-page")
def render_user_table(
    group_id: int | None = Query(None, description="Optional group ID to filter users"),
    state: TableState = Depends(UserTable.params),
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session)
):
    stmt = Q.user.select(group_id=group_id)
    table = UserTable(state, route="render_user_table", user=current_user)

    if group_id is not None:
        if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("default", group_id=group_id)

    return table.render(session, stmt)


class AssigneeTable(Table):
    key = "asg"
    model = models.User
    noun = "assignees"
    columns = [
        Col("id", "ID", sort=True, search=Exact(U.id), hideable=False, size=1),
        Col("name", "Name", sort=_FULL_NAME, search=Text(_FULL_NAME), hideable=False, size=4),
        Col("email", "Email", sort=True, search=Text(U.email), size=4),
        Col("role", "Role", sort=True, filter=Enum(C.UserRole), size=3),
    ]
    variants = {
        "seq_request": Variant(
            ["id", "name", "email", "role"], "components/tables/rows/seq_request-assignee.html",
            dom_id="seq_request-assignee-table", actions=True, toolbar="components/tables/toolbars/seq_request-assignee.html",
        ),
        "project": Variant(
            ["id", "name", "email", "role"], "components/tables/rows/project-assignee.html",
            dom_id="project-assignee-table", actions=True, toolbar="components/tables/toolbars/project-assignee.html",
        ),
    }


@router.get("/render-assignee-table-page")
def render_assignee_table(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter assignees"),
    project_id: int | None = Query(None, description="Optional project ID to filter assignees"),
    state: TableState = Depends(AssigneeTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session)
):
    stmt = Q.user.select(assignees_seq_request_id=seq_request_id, assignees_project_id=project_id)
    table = AssigneeTable(state, route="render_assignee_table", user=current_user)

    if seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use(
            "seq_request", seq_request_id=seq_request_id,
            seq_request=session.get_one(Q.seq_request.select(id=seq_request_id)),
        )
    elif project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id=project_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("project", project_id=project_id, project=session.get_one(Q.project.select(id=project_id)))
    else:
        raise exc.BadRequestException("At least one of seq_request_id or project_id must be provided")

    return table.render(session, stmt)


@router.get("/search")
def search_users(
    word: str | None = Query(None, description="Search word for user name or email"),
    group_id: int | None = Query(None, description="Optional group ID to filter users"),
    selected_id: int | None = Query(None, description="Currently selected user"),
    role_in: list[C.UserRole] | None = Depends(dependencies.parse_enum_ids(enum_type=C.UserRole, query_param="role_in")),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.user.select(
        group_id=group_id,
        role_in=role_in,
    )
    if selected_id is not None and not word:
        stmt = Q.user.select(id=selected_id, statement=stmt)
    elif word:
        stmt = Q.user.search(name=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.User.first_name.asc(), models.User.last_name.asc())
        
    if not current_user.is_insider:
        if group_id is not None:
            if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to view this resource.")
        else:    
            stmt = Q.user.select(viewer_id=current_user.id, statement=stmt)

    return query_options.search_response(session, stmt, page=page, option=query_options.user_option)


router.include_router(forms.models.UserForm.Router())
router.include_router(forms.auth.APITokenForm.Router())
router.include_router(forms.actions.MergeUsersAction.Router())