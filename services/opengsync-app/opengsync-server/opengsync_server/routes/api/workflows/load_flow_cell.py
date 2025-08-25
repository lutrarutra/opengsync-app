from flask import Blueprint, request

from opengsync_db import models

from .... import db
from ....core import wrappers, exceptions
from ....forms.workflows import load_flow_cell as wff

load_flow_cell_workflow = Blueprint("load_flow_cell_workflow", __name__, url_prefix="/api/workflows/load_flow_cell/")


@wrappers.htmx_route(load_flow_cell_workflow, db=db)
def begin(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedLoadFlowCellForm(experiment=experiment)
    else:
        form = wff.LoadFlowCellForm(experiment=experiment)
        
    return form.make_response()


@wrappers.htmx_route(load_flow_cell_workflow, db=db, methods=["POST"])
def load(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()
    
    experiment.files

    if experiment.workflow.combined_lanes:
        form = wff.UnifiedLoadFlowCellForm(experiment=experiment, formdata=request.form)
    else:
        form = wff.LoadFlowCellForm(experiment=experiment, formdata=request.form)

    return form.process_request()