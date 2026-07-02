from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/load_flow_cell", tags=["load_flow_cell"])


@router.get("/begin/{experiment_id}")
def begin_load_flow_cell_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the load flow cell workflow."""
    # TODO: Port UnifiedLoadFlowCellForm / LoadFlowCellForm to FastAPI HTMXForm
    # experiment = session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # if experiment.workflow.combined_lanes:
    #     form = UnifiedLoadFlowCellForm(experiment=experiment)
    # else:
    #     form = LoadFlowCellForm(experiment=experiment)
    # return form.make_response()
    pass