from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/lane_qc", tags=["lane_qc"])


@router.get("/begin/{experiment_id}")
async def begin_lane_qc_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the lane QC workflow."""
    # TODO: Port UnifiedQCLanesForm / QCLanesForm to FastAPI HTMXForm
    # experiment = await session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # if experiment.workflow.combined_lanes:
    #     form = UnifiedQCLanesForm(experiment=experiment)
    # else:
    #     form = QCLanesForm(experiment=experiment)
    # return await form.make_response()
    pass