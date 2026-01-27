from flask import Blueprint, render_template

from opengsync_db import models, categories as cats

from ... import db, logger
from ...core import wrappers, exceptions

design_page_bp = Blueprint("design_page", __name__)

@wrappers.page_route(design_page_bp, db=db, cache_timeout_seconds=60)
def design(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    num_flowcell_designs = db.session.query(models.FlowCellDesign).filter(
        models.FlowCellDesign.task_status_id < cats.TaskStatus.COMPLETED.id
    ).count()

    num_archived_flowcell_designs = db.session.query(models.FlowCellDesign).filter(
        models.FlowCellDesign.task_status_id >= cats.TaskStatus.COMPLETED.id
    ).count()
    return render_template("design_page.html", num_flowcell_designs=num_flowcell_designs, num_archived_flowcell_designs=num_archived_flowcell_designs)