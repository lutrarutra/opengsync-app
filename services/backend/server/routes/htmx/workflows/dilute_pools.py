from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/dilute_pools", tags=["dilute_pools"])


@router.get("/begin/{experiment_id}")
async def begin_dilute_pools_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the dilute pools workflow."""
    # TODO: Port DilutePoolsForm to FastAPI HTMXForm
    # experiment = await session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # form = DilutePoolsForm(experiment=experiment)
    # return await form.make_response()
    pass