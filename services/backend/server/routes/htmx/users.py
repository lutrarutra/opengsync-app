import io
import pandas as pd
from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query, Request, Response

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
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
    role_in: list[C.UserRole] | None = Depends(dependencies.parse_user_role_ids),
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

    
