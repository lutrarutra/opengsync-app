import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

def get_flow_cell_list_context(current_user: models.User, request: Request, archived: bool = False, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    query = db.session.query(models.FlowCellDesign)
    if not archived:
        template = "components/design/flow_cell_design-list.html"
        query = query.filter(
            models.FlowCellDesign.task_status_id < cats.TaskStatus.COMPLETED.id
        )
    else:
        template = "components/design/archived_flow_cell_design-list.html"
        query = query.filter(
            models.FlowCellDesign.task_status_id >= cats.TaskStatus.COMPLETED.id
        )
    
    flow_cell_designs = query.order_by(models.FlowCellDesign.id.desc()).all()
    
    orphan_pool_designs = db.session.query(models.PoolDesign).filter(
        models.PoolDesign.flow_cell_design_id.is_(None)
    ).all()

    return {
        "template_name_or_list": template,
        "flow_cell_designs": flow_cell_designs,
        "orphan_pool_designs": orphan_pool_designs,
    }

def get_pool_list_context(current_user: models.User, request: Request, flow_cell_design_id: int | None = None, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if flow_cell_design_id is not None:
        if (flow_cell_design := db.session.get(models.FlowCellDesign, flow_cell_design_id)) is None:
            raise exceptions.NotFoundException("Flow Cell Design not found")
    else:
        flow_cell_design = None

    query = db.session.query(models.PoolDesign)
    if flow_cell_design_id is not None:
        query = query.filter(models.PoolDesign.flow_cell_design_id == flow_cell_design_id)
    else:
        query = query.filter(models.PoolDesign.flow_cell_design_id.is_(None))
    pool_designs = query.order_by(models.PoolDesign.id.desc()).all()

    return {
        "template_name_or_list": "components/design/pool_design-list.html",
        "pool_designs": pool_designs,
        "flow_cell_design": flow_cell_design
    }
