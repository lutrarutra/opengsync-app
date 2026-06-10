from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/dist_reads", tags=["dist_reads"])


@router.get("/begin/{experiment_id}")
async def begin_dist_reads_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the distribute reads workflow."""
    # TODO: Port DistributeReadsCombinedForm / DistributeReadsSeparateForm to FastAPI
    # experiment = await session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # if experiment.workflow.combined_lanes:
    #     form = DistributeReadsCombinedForm(experiment=experiment, current_user=current_user)
    # else:
    #     form = DistributeReadsSeparateForm(experiment=experiment, current_user=current_user)
    # return await form.make_response()
    pass