from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses

router = APIRouter(prefix="/reseq", tags=["reseq"])


@router.get("/begin")
def begin_reseq_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(default=None),
    lab_prep_id: int | None = Query(default=None),
):
    """Begin the resequencing workflow."""
    # TODO: Port SelectSamplesForm and get_context to FastAPI
    # context = get_context(current_user, request.query_params)
    # form = SelectSamplesForm(
    #     "reseq", context=context,
    #     select_libraries=True,
    # )
    # return form.make_response()
    pass