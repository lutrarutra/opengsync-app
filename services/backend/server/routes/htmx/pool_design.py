from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, responses
from ... import forms

router = APIRouter(prefix="/pool_design", tags=["pool_design"], dependencies=[Depends(dependencies.require_insider)])


@router.delete("/delete-pool-design")
def delete_pool_design(
    session: SyncSession = Depends(dependencies.db_session),
    pool_design_id: int = Query(...),
):
    """Permanently delete a pool design."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    session.delete(pd)
    return responses.htmx_response(redirect=responses.url_for("design"))


@router.delete("/remove-pool-design")
def remove_pool_design(
    session: SyncSession = Depends(dependencies.db_session),
    pool_design_id: int = Query(...),
):
    """Remove a pool design from its flow cell design (unlink, don't delete)."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    pd.flow_cell_design = None
    return responses.htmx_response(redirect=responses.url_for("design"))


@router.post("/move-pool-design")
def move_pool_design(
    session: SyncSession = Depends(dependencies.db_session),
    pool_design_id: int = Query(...),
    new_flow_cell_design_id: int = Query(...),
):
    """Move a pool design to a different flow cell design."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    new_fcd = session.get_one(Q.flow_cell_design.select(id=new_flow_cell_design_id))
    pd.flow_cell_design = new_fcd
    return responses.htmx_response(redirect=responses.url_for("design"))

@router.get("/render-pool-designs")
def render_pool_designs(
    session: SyncSession = Depends(dependencies.db_session),
    flow_cell_design_id: int | None = Query(None),
):
    """Render the list of pool designs for a flow cell (or orphans)."""
    flow_cell_design = None

    if flow_cell_design_id is not None:
        flow_cell_design = session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))

    stmt = Q.pool_design.select(
        flow_cell_design_id=flow_cell_design_id,
        orphan=flow_cell_design_id is None,
    ).order_by(models.PoolDesign.id.desc())

    pool_designs = session.get_all(
        stmt.options(
            orm.selectinload(models.PoolDesign.pool).selectinload(models.Pool.experiment),
            orm.selectinload(models.PoolDesign.comments).selectinload(models.TODOComment.author),
            orm.selectinload(models.PoolDesign.flow_cell_design).with_expression(models.FlowCellDesign._r1_cycles, models.FlowCellDesign.r1_cycles.expression),
            orm.selectinload(models.PoolDesign.flow_cell_design).with_expression(models.FlowCellDesign._r2_cycles, models.FlowCellDesign.r2_cycles.expression),
            orm.selectinload(models.PoolDesign.flow_cell_design).with_expression(models.FlowCellDesign._i1_cycles, models.FlowCellDesign.i1_cycles.expression),
            orm.selectinload(models.PoolDesign.flow_cell_design).with_expression(models.FlowCellDesign._i2_cycles, models.FlowCellDesign.i2_cycles.expression),
        )
    )
    return responses.htmx_response(
        template="components/design/pool_design-list.html",
        pool_designs=pool_designs,
        flow_cell_design=flow_cell_design,
    )

router.include_router(forms.models.PoolDesignForm.Router())