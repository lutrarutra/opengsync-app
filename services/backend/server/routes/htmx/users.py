from loguru import logger
from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc, mailer, secrets
from ...components.tables import HTMXTable, TableCol
from ...core.context import ctx
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
async def render_user_table(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter projects"),
    project_id: int | None = Query(None, description="Optional project ID to filter projects"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_insider),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.User, default=models.User.id.desc())),
    role_in: list[C.UserRole] | None = Depends(dependencies.parse_enum_ids(enum_type=C.UserRole, query_param="role_in")),
    session: AsyncSession = Depends(dependencies.db_session)
):
    table = UserTable(route="render_user_table", page=page, order_by=order_by)

    stmt = Q.user.select(
        assignees_seq_request_id=seq_request_id,
        assignees_project_id=project_id,
        role_in=role_in,
    )

    if role_in:
        table.filter_values["role"] = role_in

    if seq_request_id is not None:
        template = "components/tables/seq-request-assignee.html"
        table.url_params["seq_request_id"] = seq_request_id
    elif project_id is not None:
        template = "components/tables/project-assignee.html"
        table.url_params["project_id"] = project_id
    else:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        template = "components/tables/user.html"


    users, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[

        ]
    )
    table.set_num_pages(count)
    return await responses.htmx_response(template=template, users=users, table=table)

    
@router.get("/search")
async def search_users(
    word: str | None = Query(None, description="Search word for user name or email"),
    group_id: int | None = Query(None, description="Optional group ID to filter users"),
    selected_id: int | None = Query(None, description="Currently selected user"),
    role_in: list[C.UserRole] | None = Depends(dependencies.parse_enum_ids(enum_type=C.UserRole, query_param="role_in")),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: AsyncSession = Depends(dependencies.db_session),
):
    stmt = Q.user.select(
        group_id=group_id,
        role_in=role_in,
    )
    if selected_id is not None and not word:
        stmt = Q.user.select(id=selected_id, statement=stmt)
    elif word is not None:
        stmt = Q.user.search(name=word, statement=stmt)
        
    if not current_user.is_insider():
        if group_id is not None:
            if await session.get_access_level(Q.group.permissions(group_id=group_id, user_id=current_user.id)) < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to view this resource.")
        else:    
            stmt = Q.user.select(viewer_id=current_user.id, statement=stmt)

    users, count = await session.page(stmt, page=page)
    return await responses.htmx_response(template="components/search/user.html", users=users)


@router.get("/{user_id}/edit")
async def render_edit_user_form(
    user_id: int,
    request: Request,
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to edit this user.")
    
    user = await session.get_one(Q.user.select(id=user_id))

    form = forms.models.UserForm(request, user)
    return await responses.htmx_response(template="forms/user.html", form=form)


@router.post("/{user_id}/edit")
async def edit_user(response = Depends(forms.models.UserForm.edit_user)): return response

@router.get("/{user_id}/change-password")
async def render_change_password_form(
    user_id: int,
    request: Request,
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to change this user's password.")
    
    user = await session.get_one(Q.user.select(id=user_id))

    form = forms.auth.ChangePasswordForm(request, user)
    return await responses.htmx_response(template="forms/auth/change_password.html", form=form)


@router.post("/{user_id}/change-password")
async def change_password(response = Depends(forms.auth.ChangePasswordForm.change_password)): return response


@router.post("/{user_id}/reset-password")
async def send_reset_password_email(
    user_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
    email: mailer.Mailer = Depends(dependencies.mail_client),
):
    if current_user.id != user_id and access_level < C.AccessLevel.ADMIN:
        raise exc.NoPermissionsException("You do not have permission to change this user's password.")
    
    user = await session.get_one(Q.user.select(id=user_id))
        
    token = secrets.create_password_reset_token(user_id=user.id)
    link = responses.url_for("reset_password_page", token=token)
    await email.send_password_reset(recipient_email=user.email, reset_link=link)

    return await responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Password reset email sent!", "success"),
    )

@router.post("/{user_id}/activate")
async def activate_user(
    user_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    email: mailer.Mailer = Depends(dependencies.mail_client),
):
    
    user = await session.get_one(Q.user.select(id=user_id))

    if user.role != C.UserRole.DEACTIVATED:
        raise exc.BadRequestException("User is already active.")
    
    user.role = C.UserRole.CLIENT

    token = secrets.create_password_reset_token(user_id=user.id)
    link = responses.url_for("reset_password_page", token=token)
    await email.send_password_reset(recipient_email=user.email, reset_link=link)

    return await responses.htmx_response(
        redirect=responses.url_for("login_page"),
        flash=responses.flash("Check your email!", "success"),
    )
    

@router.post("/{user_id}/start-user-session")
async def start_user_session(
    user_id: int,
    current_user: models.User = Depends(dependencies.require_admin),
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
):
    user = await session.get_one(Q.user.select(id=user_id))

    logger.info(f"Admin {current_user.email} is starting a session for user {user.email}")
    pass
    # TODO: missing implementation


@router.get("/{user_id}/create-api-token")
async def render_create_api_token_form(
    user_id: int,
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
):
    if current_user.id != user_id and access_level < C.AccessLevel.ADMIN:
        raise exc.NoPermissionsException("You do not have permission to create API tokens for this user.")
    
    user = await session.get_one(Q.user.select(id=user_id))

    form = forms.auth.APITokenForm(request, user)
    return await responses.htmx_response(template="forms/auth/create_api_token.html", form=form)

@router.post("/{user_id}/create-api-token")
async def create_api_token(response = Depends(forms.auth.APITokenForm.create_api_token)): return response


@router.get("/{user_id}/api-tokens")
async def render_api_tokens_table(
    user_id: int,
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
):
    # TODO: missing implementation
    pass
