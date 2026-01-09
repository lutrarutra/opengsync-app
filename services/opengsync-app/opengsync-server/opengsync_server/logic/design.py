from flask import Request

from opengsync_db import models

from ..import db, logger
from ..core import exceptions

def get_flow_cell_list_context(current_user: models.User, request: Request, archived: bool = False, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if not archived:
        template = "components/design/flow_cell_design-list.html"
    else:
        template = "components/design/archived_flow_cell_design-list.html"
    
    flow_cell_designs, _ = db.flow_cell_designs.find(archived=archived, limit=None)
    
    return {
        "template_name_or_list": template,
        "flow_cell_designs": flow_cell_designs,
    }

def get_pool_list_context(current_user: models.User, request: Request, flow_cell_design_id: int | None = None, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    orphan_pool_only = None
    if flow_cell_design_id is not None:
        if (flow_cell_design := db.flow_cell_designs.get(flow_cell_design_id)) is None:
            raise exceptions.NotFoundException("Flow Cell Design not found")
    else:
        flow_cell_design = None
        orphan_pool_only = True

    pool_designs, _ = db.pool_designs.find(flow_cell_design_id=flow_cell_design_id, orphan=orphan_pool_only)

    return {
        "template_name_or_list": "components/design/pool_design-list.html",
        "pool_designs": pool_designs,
        "flow_cell_design": flow_cell_design
    }
