from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ....core import dependencies, responses

router = APIRouter(prefix="/merge_projects", tags=["merge_projects"])


@router.get("/begin")
def begin_merge_projects_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
):
    """Begin the merge projects workflow."""
    # TODO: Port MergeProjectsForm to FastAPI HTMXForm
    # form = MergeProjectsForm()
    # return form.make_response()
    pass