from sqlalchemy import orm
from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ... import forms


router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=1, searchable=True, sortable=True),
        TableCol(title="Title", label="title", col_size=3, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sort_by="status_id", sortable=True, choices=C.ProjectStatus.as_selectable()),
        TableCol(title="Group", label="group", col_size=2),
        TableCol(title="Owner", label="owner_name", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
    ]



@router.get("/render-table-page")
async def render_project_table(
    user_id: int | None = Query(None, description="Optional User ID for whom to render the project table"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter projects"),
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter projects"),
    group_id: int | None = Query(None, description="Optional group ID to filter projects"),
    status_in: list[C.ProjectStatus] | None = Depends(dependencies.parse_project_status_ids),
    library_types_in: list[C.LibraryType] | None = Depends(dependencies.parse_library_type_ids),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Project, default=models.Project.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = ProjectTable(route="render_project_table", page=page, order_by=order_by)
    
    stmt = Q.project.select(
        user_id=user_id,
        experiment_id=experiment_id,
        seq_request_id=seq_request_id,
        group_id=group_id,
        status_in=status_in,
        library_types_in=library_types_in,
    )
    
    if user_id is not None:
        template = "components/tables/user-project.html"
        stmt = Q.project.select(user_id=user_id, statement=stmt)
        table.url_params["user_id"] = user_id
    elif experiment_id is not None:
        template = "components/tables/experiment-project.html"        
        stmt = Q.project.select(experiment_id=experiment_id, statement=stmt)
        table.url_params["experiment_id"] = experiment_id
    elif seq_request_id is not None:
        template = "components/tables/seq_request-project.html"
        stmt = Q.project.select(seq_request_id=seq_request_id, statement=stmt)
        table.url_params["seq_request_id"] = seq_request_id
    elif group_id is not None:
        template = "components/tables/group-project.html"
        stmt = Q.project.select(group_id=group_id, statement=stmt)
        table.url_params["group_id"] = group_id
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            stmt = Q.project.select(user_id=current_user.id, statement=stmt)

    projects, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Project.assignees),
            orm.selectinload(models.Project.libraries),
            orm.selectinload(models.Project.owner),
            orm.selectinload(models.Project.group),
            orm.with_expression(models.Project.num_samples_, models.Project.num_samples.expression),
        ]
    )
    table.set_num_pages(count)
    
    return await responses.htmx_response(
        template=template,
        projects=projects,
        table=table,
    )
    
    
@router.get("/create")
async def render_create_project_form(
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
):
    """Render the create project form."""
    form = forms.models.ProjectForm(request, form_type="create")
    return await form.make_response()