from flask import Request

from opengsync_db import models, queries as Q

from ..import db
from ..core import exceptions

def get_flow_cell_list_context(current_user: models.User, request: Request, archived: bool = False, **kwargs) -> dict:
    if not current_user.is_insider:
        raise exceptions.NoPermissionsException()
    
    if not archived:
        template = "components/design/flow_cell_design-list.html"
    else:
        template = "components/design/archived_flow_cell_design-list.html"
    
    designs = db.session.get_all(
        Q.flow_cell_design.select(archived=archived).order_by(models.FlowCellDesign.id.desc())
    )
    
    return {
        "template_name_or_list": template,
        "flow_cell_designs": designs,
    }

def get_pool_list_context(current_user: models.User, request: Request, flow_cell_design_id: int | None = None, **kwargs) -> dict:
    if not current_user.is_insider:
        raise exceptions.NoPermissionsException()
    
    orphan_pool_only = None
    if flow_cell_design_id is not None:
        if (flow_cell_design := db.session.first(Q.flow_cell_design.select(id=flow_cell_design_id))) is None:
            raise exceptions.NotFoundException("Flow Cell Design not found")
    else:
        flow_cell_design = None
        orphan_pool_only = True

    designs = db.session.get_all(
        Q.pool_design.select(
            flow_cell_design_id=flow_cell_design_id,
            orphan=orphan_pool_only
        ).order_by(models.PoolDesign.id.desc())
    )

    return {
        "template_name_or_list": "components/design/pool_design-list.html",
        "pool_designs": designs,
        "flow_cell_design": flow_cell_design
    }
