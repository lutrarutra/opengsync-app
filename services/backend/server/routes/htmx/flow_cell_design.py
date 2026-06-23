from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc
from ...forms.models import FlowCellDesignForm

router = APIRouter(prefix="/flow_cell_design", tags=["flow_cell_design"])

async def _get_flow_cell_designs(
    session: AsyncSession, archived: bool = False,
) -> list[models.FlowCellDesign]:
    """Fetch flow cell designs with eager-loaded pool_designs and comments."""
    stmt = Q.flow_cell_design.select(archived=archived).order_by(models.FlowCellDesign.id.desc())
    result = await session.get_all(
        stmt.options(
            orm.selectinload(models.FlowCellDesign.pool_designs).selectinload(models.PoolDesign.pool),
            orm.selectinload(models.FlowCellDesign.comments).selectinload(models.TODOComment.author),
            orm.with_expression(models.FlowCellDesign._num_m_reads, models.FlowCellDesign.num_m_reads.expression)
        )
    )
    return list(result)

@router.get("/flow-cells")
async def flow_cells(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Render the active (non-archived) flow cell design list."""
    flow_cell_designs = await _get_flow_cell_designs(session, archived=False)
    return await responses.htmx_response(
        template="components/design/flow_cell_design-list.html",
        flow_cell_designs=flow_cell_designs,
    )


@router.get("/archived-flow-cells")
async def archived_flow_cells(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Render the archived flow cell design list."""
    flow_cell_designs = await _get_flow_cell_designs(session, archived=True)
    return await responses.htmx_response(
        template="components/design/archived_flow_cell_design-list.html",
        flow_cell_designs=flow_cell_designs,
    )


@router.post("/create-flow-cell-design")
async def create_flow_cell_design(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    pool_design_id: int = Query(...),
):
    """Create a new flow cell design and assign a pool design to it."""
    pool_design = await session.get_one(Q.pool_design.select(id=pool_design_id))

    count = await session.count(Q.flow_cell_design.select())
    name = f"Flow Cell Design {count + 1}"

    flow_cell_design = Q.flow_cell_design.create(
        name=name[: models.FlowCellDesign.name.type.length],
    )
    flow_cell_design.pool_designs = [pool_design]
    session.add(flow_cell_design)

    return await responses.htmx_response(redirect=responses.url_for("design"))


@router.get("/edit-flow-cell-design", name="edit_flow_cell_design")
async def edit_flow_cell_design_get(
    request: Request,
    flow_cell_design_id: int = Query(...),
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Render the edit flow cell design form."""
    design = await session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))
    form = FlowCellDesignForm(request, flow_cell_design=design)
    return await form.make_response()


@router.post("/edit-flow-cell-design")
async def edit_flow_cell_design_post(
    request: Request,
    flow_cell_design_id: int = Query(...),
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Process the edit flow cell design form."""
    design = await session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))
    form = FlowCellDesignForm(request, flow_cell_design=design)
    return await form.process_request()


@router.post("/set-flow-cell-type")
async def set_flow_cell_type(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    flow_cell_design_id: int = Query(...),
    flow_cell_type_id: int = Query(...),
):
    """Set the flow cell type for a design."""
    design = await session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))

    if flow_cell_type_id == -1:
        design.flow_cell_type = None
    else:
        design.flow_cell_type = C.FlowCellType.get(flow_cell_type_id)

    return await responses.htmx_response(redirect=responses.url_for("design"))


@router.post("/archive-flow-cell-design")
async def archive_flow_cell_design(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    flow_cell_design_id: int = Query(...),
):
    """Archive a flow cell design."""
    design = await session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))
    design.task_status = C.TaskStatus.ARCHIVED
    return await responses.htmx_response(redirect=responses.url_for("design"))


@router.post("/unarchive-flow-cell-design")
async def unarchive_flow_cell_design(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    flow_cell_design_id: int = Query(...),
):
    """Unarchive a flow cell design."""
    design = await session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))
    design.task_status = C.TaskStatus.DRAFT
    return await responses.htmx_response(redirect=responses.url_for("design"))


@router.delete("/delete-flow-cell-design")
async def delete_flow_cell_design(
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    flow_cell_design_id: int = Query(...),
):
    """Permanently delete a flow cell design."""
    design = await session.get_one(
        Q.flow_cell_design.select(id=flow_cell_design_id).options(
            orm.selectinload(models.FlowCellDesign.pool_designs),
        )
    )
    for pd in design.pool_designs:
        pd.flow_cell_design = None
    await session.delete(design)
    return await responses.htmx_response(redirect=responses.url_for("design"))