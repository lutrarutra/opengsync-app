from fastapi import APIRouter, Depends, Query

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ... import forms


router = APIRouter(prefix="/users", tags=["users"])

class UserTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True),
        TableCol(title="Email", label="email", col_size=3, sortable=True),
        TableCol(title="Role", label="role", col_size=2, choices=C.UserRole.as_selectable(), sortable=True, sort_by="role_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
    ]



@router.get("/render-table-page")
def render_user_table(
    group_id: int | None = Query(None, description="Optional group ID to filter users"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_insider),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.User, default=models.User.id.desc())),
    role_in: list[C.UserRole] | None = Depends(dependencies.parse_enum_ids(enum_type=C.UserRole, query_param="role_in")),
    session: SyncSession = Depends(dependencies.db_session)
):
    table = UserTable(route="render_user_table", page=page, order_by=order_by)

    stmt = Q.user.select(
        role_in=role_in,
        group_id=group_id,
    )

    if role_in:
        table.filter_values["role"] = role_in

    if group_id is not None:
        if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/group-user.html"
        table.url_params["group_id"] = group_id
        table.context["group"] = session.get_one(Q.group.select(id=group_id))
    else:
        table.template = "components/tables/user.html"

    users = table.paginate(session, stmt, page=page, order_by=order_by)
    return table.make_response(users=users)


class AssigneeTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=4, searchable=True),
        TableCol(title="Email", label="email", col_size=4, sortable=True),
        TableCol(title="Role", label="role", col_size=3, choices=C.UserRole.as_selectable(), sortable=True, sort_by="role_id"),
    ]


@router.get("/render-assignee-table-page")
def render_assignee_table(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter assignees"),
    project_id: int | None = Query(None, description="Optional project ID to filter assignees"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.User, default=models.User.id.desc())),
    role_in: list[C.UserRole] | None = Depends(dependencies.parse_enum_ids(enum_type=C.UserRole, query_param="role_in")),
    session: SyncSession = Depends(dependencies.db_session)
):
    table = AssigneeTable(route="render_assignee_table", page=page, order_by=order_by)

    stmt = Q.user.select(
        assignees_seq_request_id=seq_request_id,
        assignees_project_id=project_id,
        role_in=role_in,
    )

    if role_in:
        table.filter_values["role"] = role_in

    if seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/seq_request-assignee.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request"] = session.get_one(Q.seq_request.select(id=seq_request_id))
    elif project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id=project_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/project-assignee.html"
        table.url_params["project_id"] = project_id
        table.context["project"] = session.get_one(Q.project.select(id=project_id))
    else:
        raise exc.BadRequestException("At least one of seq_request_id or project_id must be provided")

    users = table.paginate(session, stmt, page=page, order_by=order_by)
    return table.make_response(users=users)

    
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
    elif word is not None:
        stmt = Q.user.search(name=word, statement=stmt)
        
    if not current_user.is_insider:
        if group_id is not None:
            if session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to view this resource.")
        else:    
            stmt = Q.user.select(viewer_id=current_user.id, statement=stmt)

    users, _ = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/user.html", users=users)


router.include_router(forms.models.UserForm.Router())
router.include_router(forms.auth.APITokenForm.Router())