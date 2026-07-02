from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, responses, exceptions as exc
from ...forms.models import PoolDesignForm

router = APIRouter(prefix="/pool_design", tags=["pool_design"])


@router.get("/create-pool-design", name="create_pool_design")
def create_pool_design_get(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Render the create pool design form."""
    form = PoolDesignForm(request, pool_design=None)
    return form.make_response()


@router.post("/create-pool-design")
def create_pool_design_post(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Process the create pool design form."""
    form = PoolDesignForm(request, pool_design=None)
    return form.process_request()


@router.get("/edit-pool-design", name="edit_pool_design")
def edit_pool_design_get(
    request: Request,
    pool_design_id: int = Query(...),
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Render the edit pool design form."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    form = PoolDesignForm(request, pool_design=pd)
    return form.make_response()


@router.post("/edit-pool-design")
def edit_pool_design_post(
    request: Request,
    pool_design_id: int = Query(...),
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Process the edit pool design form."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    form = PoolDesignForm(request, pool_design=pd)
    return form.process_request()


@router.delete("/delete-pool-design")
def delete_pool_design(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
    pool_design_id: int = Query(...),
):
    """Permanently delete a pool design."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    session.delete(pd)
    return responses.htmx_response(redirect=responses.url_for("design"))


@router.delete("/remove-pool-design")
def remove_pool_design(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
    pool_design_id: int = Query(...),
):
    """Remove a pool design from its flow cell design (unlink, don't delete)."""
    pd = session.get_one(Q.pool_design.select(id=pool_design_id))
    pd.flow_cell_design = None
    return responses.htmx_response(redirect=responses.url_for("design"))


@router.post("/move-pool-design")
def move_pool_design(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
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
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
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