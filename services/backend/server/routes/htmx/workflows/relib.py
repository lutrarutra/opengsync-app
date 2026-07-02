from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses

router = APIRouter(prefix="/relib", tags=["relib"])


@router.get("/begin")
def begin_relib_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(default=None),
    lab_prep_id: int | None = Query(default=None),
):
    """Begin the re-library workflow."""
    # TODO: Port SelectSamplesForm and get_context to FastAPI
    # context = get_context(request.query_params)
    # form = SelectSamplesForm("relib", context=context, select_libraries=True)
    # return form.make_response()
    pass