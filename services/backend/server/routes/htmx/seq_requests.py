from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ... import forms
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/seq_requests", tags=["seq_requests"])


class SeqRequestTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=4, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=C.SeqRequestStatus.as_selectable()),
        TableCol(title="Submission Type", label="submission_type", col_size=1, choices=C.SubmissionType.as_selectable()),
        TableCol(title="Group", label="group", col_size=2, searchable=True),
        TableCol(title="Requestor", label="requestor", col_size=2, searchable=True),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Submitted", label="timestamp_submitted", col_size=2, sortable=True, sort_by="timestamp_submitted_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]



@router.get("/render-table-page")
async def render_seq_request_table(
    user_id: int | None = Query(None, description="Optional user ID to filter seq requests"),
    group_id: int | None = Query(None, description="Optional group ID to filter seq requests"),
    project_id: int | None = Query(None, description="Optional project ID to filter seq requests"),
    status_in: list[C.SeqRequestStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.SeqRequestStatus, query_param="status_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.SeqRequest, default=models.SeqRequest.timestamp_submitted_utc.desc())),
    session: AsyncSession = Depends(dependencies.db_session),
):
    table = SeqRequestTable(route="render_seq_request_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    
    stmt = Q.seq_request.select(
        requestor_id=user_id,
        group_id=group_id,
        project_id=project_id,
        status_in=status_in,
    )

    if user_id is not None:
        if await session.get_access_level(Q.user.permissions(user_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this user.")
        template = "components/tables/user-seq-request.html"
    elif group_id is not None:
        if await session.get_access_level(Q.group.permissions(group_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this group.")
        template = "components/tables/group-seq-request.html"
    elif project_id is not None:
        if await session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view seq requests for this project.")
        template = "components/tables/project-seq-request.html"
    else:
        if not current_user.is_insider():
            stmt = Q.seq_request.select(viewer_id=current_user.id, statement=stmt)

        template = "components/tables/seq_request-table.html"

    seq_requests, count = await session.page(
        stmt, page=page, order_by=order_by,
        options=[

        ]
    )
    table.set_num_pages(count)
    return await responses.htmx_response(template=template, seq_requests=seq_requests, table=table)

@router.get("/recent")
async def recent_seq_requests(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session)
):
    options = [
        orm.selectinload(models.SeqRequest.assignees),
        orm.selectinload(models.SeqRequest.requestor),
        orm.with_expression(models.SeqRequest._num_libraries, models.SeqRequest.num_libraries.expression),
    ]
    if current_user.is_insider():        
        query = Q.seq_request.select(
            status_in=[
                C.SeqRequestStatus.SUBMITTED, C.SeqRequestStatus.ACCEPTED,
                C.SeqRequestStatus.SAMPLES_RECEIVED, C.SeqRequestStatus.PREPARED,
                C.SeqRequestStatus.DATA_PROCESSING
            ]
        ).order_by(
            models.SeqRequest.status_id,
            models.SeqRequest.timestamp_submitted_utc.desc()
        )
        
    else:
        query = Q.seq_request.select(
            status_in=[
                C.SeqRequestStatus.SUBMITTED, C.SeqRequestStatus.ACCEPTED,
                C.SeqRequestStatus.SAMPLES_RECEIVED, C.SeqRequestStatus.PREPARED,
                C.SeqRequestStatus.DATA_PROCESSING
            ],
            requestor_id=current_user.id
        ).order_by(
            models.SeqRequest.status_id,
            models.SeqRequest.timestamp_submitted_utc.desc()
        )

    seq_requests, num_total = await session.page(query, limit=10, page=page, options=options)

    return await responses.htmx_response("components/dashboard/seq_requests-list.html", seq_requests=seq_requests, num_total=num_total, current_page=page, limit=10)


@router.get("/create")
async def get_seq_request_form(
    request: Request,
    current_user: models.User = Depends(dependencies.require_user),
):
    """Render the create SeqRequest form."""
    form = forms.models.SeqRequestForm(request, form_type="create")
    await form.prepare(current_user)
    return await form.make_response()


@router.post("/create")
async def create_seq_request(
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_user),
):
    """Process the create SeqRequest form."""
    return await forms.models.SeqRequestForm.process_request(
        request=request,
        session=session,
        current_user=current_user,
        form_type="create",
    )

@router.get("/edit/{seq_request_id}")
async def get_edit_seq_request_form(
    request: Request,
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_user),
):
    """Render the edit SeqRequest form."""
    from sqlalchemy import select as sa_select

    seq_request = await session.first(
        sa_select(models.SeqRequest).where(models.SeqRequest.id == seq_request_id)
    )
    if seq_request is None:
        return responses.htmx_response(redirect=responses.url_for("seq_requests_page"))

    is_insider = current_user.is_insider
    if not is_insider and seq_request.requestor_id != current_user.id:
        return responses.htmx_response(redirect=responses.url_for("seq_requests_page"))

    if not seq_request.is_editable:
        return responses.htmx_response(redirect=responses.url_for("seq_request_page", seq_request_id=seq_request_id))

    form = forms.models.SeqRequestForm(request, form_type="edit", seq_request_id=seq_request_id)
    await form.fill_from_seq_request(seq_request)
    return await form.make_response()


@router.post("/edit/{seq_request_id}")
async def edit_seq_request(
    request: Request,
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_user),
):
    """Process the edit SeqRequest form."""
    return await forms.models.SeqRequestForm.process_request(
        request=request,
        session=session,
        current_user=current_user,
        form_type="edit",
        seq_request_id=seq_request_id,
    )


@router.post("/add-assignee")
async def add_assignee_to_seq_request(
    seq_request_id: int = Query(...),
    assignee_id: int | None = Query(None),
    session: AsyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Add an assignee to a SeqRequest."""
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))
    
    if assignee_id is not None:
        assignee = await session.get_one(Q.user.select(id=assignee_id))
    else:
        assignee = current_user
    
    if not assignee.is_insider():
        raise exc.NoPermissionsException("Assignee must be an insider.")
    
    if assignee in seq_request.assignees:
        raise exc.BadRequestException("User is already an assignee.")
    
    seq_request.assignees.append(assignee)
    await session.save(seq_request)

    return await responses.htmx_response(
        redirect=responses.url_for("dashboard"),
        flash=responses.flash("Assignee Added!", "success")
    )