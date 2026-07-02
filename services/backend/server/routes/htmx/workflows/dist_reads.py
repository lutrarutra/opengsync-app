from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/dist_reads", tags=["dist_reads"])


@router.get("/begin/{experiment_id}")
def begin_dist_reads_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the distribute reads workflow."""
    # TODO: Port DistributeReadsCombinedForm / DistributeReadsSeparateForm to FastAPI
    # experiment = session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # if experiment.workflow.combined_lanes:
    #     form = DistributeReadsCombinedForm(experiment=experiment, current_user=current_user)
    # else:
    #     form = DistributeReadsSeparateForm(experiment=experiment, current_user=current_user)
    # return form.make_response()
    pass