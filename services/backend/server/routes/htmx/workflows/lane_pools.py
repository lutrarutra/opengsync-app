from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/lane_pools", tags=["lane_pools"])


@router.get("/begin/{experiment_id}")
def begin_lane_pools_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the lane pooling workflow."""
    # TODO: Port UnifiedLanePoolingForm / LanePoolingForm to FastAPI HTMXForm
    # experiment = session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # if experiment.workflow.combined_lanes:
    #     form = UnifiedLanePoolingForm(experiment=experiment)
    # else:
    #     form = LanePoolingForm(experiment=experiment)
    # return form.make_response()
    pass