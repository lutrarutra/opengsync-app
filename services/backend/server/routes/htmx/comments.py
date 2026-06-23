from sqlalchemy import select as sa_select

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc, config
from ...components.tables import HTMXTable, TableCol
from ... import forms


router = APIRouter(prefix="/comments", tags=["comments"])

@router.get("/form")
async def render_comment_form(
    request: Request,
    seq_request_id: int | None = Query(None),
    experiment_id: int | None = Query(None),
    lab_prep_id: int | None = Query(None),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session),
) -> Response:
    """Render the comment form for a seq request, experiment, or lab prep."""
    await forms.models.CommentForm.check_permissions(
        current_user=current_user,
        session=session,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
    )
    form = forms.models.CommentForm(
        request,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
    )
    return await form.make_response()


@router.post("/form")
async def submit_comment_form(response: Response = Depends(forms.models.CommentForm.submit_form)) -> Response:
    """Process the comment form submission."""
    return response


@router.get("/render-thread")
async def render_comment_thread(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter comments"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter comments"),
    lab_prep_id: int | None = Query(None, description="Optional lab prep ID to filter comments"),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session)
) -> Response:

    if seq_request_id is not None:
        if await session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        comments = await session.get_all(Q.comment.select(seq_request_id=seq_request_id))
    elif experiment_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        comments = await session.get_all(Q.comment.select(experiment_id=experiment_id))
    elif lab_prep_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        comments = await session.get_all(Q.comment.select(lab_prep_id=lab_prep_id))
    else:
        raise exc.BadRequestException("At least one of seq_request_id, experiment_id, or lab_prep_id must be provided.")

    return await responses.htmx_response("components/comment-thread.html", comments=comments)

@router.get("/form", name="comment_form", dependencies=[Depends(dependencies.require_insider)])
async def render_todo_comment_form(
    request: Request,
    session: AsyncSession = Depends(dependencies.db_session),
    todo_comment_id: int | None = Query(None),
    flow_cell_design_id: int | None = Query(None),
    pool_design_id: int | None = Query(None),
) -> Response:
    """Render the TODO comment form for a flow cell or pool design."""
    todo_comment: models.TODOComment | None = None
    flow_cell_design: models.FlowCellDesign | None = None
    pool_design: models.PoolDesign | None = None

    if todo_comment_id is not None:
        result = await session.execute(
            sa_select(models.TODOComment).where(models.TODOComment.id == todo_comment_id)
        )
        todo_comment = result.scalar_one_or_none()
        if todo_comment is None:
            raise exc.ItemNotFoundException("TODO Comment not found")

    if flow_cell_design_id is not None:
        flow_cell_design = await session.get_one(
            Q.flow_cell_design.select(id=flow_cell_design_id)
        )

    if pool_design_id is not None:
        pool_design = await session.get_one(
            Q.pool_design.select(id=pool_design_id)
        )

    form = forms.models.TODOCommentForm(
        request,
        todo_comment=todo_comment,
        flow_cell_design_id=flow_cell_design_id,
        pool_design_id=pool_design_id,
    )
    return await form.make_response()


@router.post("/form")
async def submit_todo_comment_form(
    response: Response = Depends(forms.models.TODOCommentForm.submit_form),
) -> Response:
    """Process the TODO comment form submission."""
    return response


@router.post("/edit-status", name="edit_comment_status", dependencies=[Depends(dependencies.require_insider)])
async def edit_todo_comment_status(
    session: AsyncSession = Depends(dependencies.db_session),
    todo_comment_id: int = Query(...),
    new_status_id: int | None = Query(None),
) -> Response:
    """Change the status of a TODO comment."""
    result = await session.execute(
        sa_select(models.TODOComment).where(models.TODOComment.id == todo_comment_id)
    )
    todo_comment = result.scalar_one_or_none()
    if todo_comment is None:
        raise exc.ItemNotFoundException("TODO Comment not found")

    todo_comment.task_status_id = new_status_id

    # Re-render the full flow cell design list to reflect the change
    stmt = Q.flow_cell_design.select(archived=False).order_by(models.FlowCellDesign.id.desc())
    result = await session.execute(
        stmt.options(
            orm.selectinload(models.FlowCellDesign.pool_designs).selectinload(models.PoolDesign.pool),
            orm.selectinload(models.FlowCellDesign.comments).selectinload(models.TODOComment.author),
        )
    )
    flow_cell_designs = list(result.scalars().all())

    return await responses.htmx_response(
        template="components/design/flow_cell_design-list.html",
        flow_cell_designs=flow_cell_designs,
    )


@router.delete("/delete", name="delete_comment", dependencies=[Depends(dependencies.require_insider)])
async def delete_todo_comment(
    session: AsyncSession = Depends(dependencies.db_session),
    todo_comment_id: int = Query(...),
) -> Response:
    """Delete a TODO comment permanently."""
    result = await session.execute(
        sa_select(models.TODOComment).where(models.TODOComment.id == todo_comment_id)
    )
    todo_comment = result.scalar_one_or_none()
    if todo_comment is None:
        raise exc.ItemNotFoundException("TODO Comment not found")

    await session.delete(todo_comment)
    return await responses.htmx_response(redirect=responses.url_for("design"))