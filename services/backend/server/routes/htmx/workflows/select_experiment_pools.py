from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/select_experiment_pools", tags=["select_experiment_pools"])


@router.get("/begin/{experiment_id}")
def begin_select_experiment_pools_workflow(
    request: Request,
    experiment_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the select experiment pools workflow."""
    # TODO: Port SelectSamplesForm to FastAPI HTMXForm
    # experiment = session.first(Q.experiment.select(id=experiment_id))
    # if experiment is None:
    #     raise exc.NotFoundException()
    # form = SelectSamplesForm.create_workflow_form(
    #     workflow="select_experiment_pools",
    #     context={"experiment": experiment},
    # )
    # return form.make_response()
    pass