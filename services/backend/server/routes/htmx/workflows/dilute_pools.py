from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/dilute_pools", tags=["dilute_pools"])


@router.get("/begin/{experiment_id}")
def begin_dilute_pools_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the dilute pools workflow."""
    # TODO: Port DilutePoolsForm to FastAPI HTMXForm
    # experiment = session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # form = DilutePoolsForm(experiment=experiment)
    # return form.make_response()
    pass