from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc
from ... import forms

router = APIRouter(prefix="/seq_requests", tags=["seq_requests"])

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


# ---------------------------------------------------------------------------
# Create SeqRequest
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Edit SeqRequest
# ---------------------------------------------------------------------------

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
        return responses.htmx_response(redirect="/seq-requests")

    is_insider = current_user.is_insider
    if not is_insider and seq_request.requestor_id != current_user.id:
        return responses.htmx_response(redirect="/seq-requests")

    if not seq_request.is_editable:
        return responses.htmx_response(redirect=f"/seq-requests/{seq_request_id}")

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
        raise exc.PermissionDeniedException("Assignee must be an insider.")
    
    if assignee in seq_request.assignees:
        raise exc.BadRequestException("User is already an assignee.")
    
    seq_request.assignees.append(assignee)
    await session.save(seq_request)
    # flash("Assignee Added.", "success")
    return await responses.htmx_response(redirect="dashboard")