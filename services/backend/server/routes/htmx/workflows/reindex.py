from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession

from ....core import dependencies, responses

router = APIRouter(prefix="/reindex", tags=["reindex"])


@router.get("/begin")
async def begin_reindex_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(default=None),
    lab_prep_id: int | None = Query(default=None),
    pool_id: int | None = Query(default=None),
):
    """Begin the reindex workflow."""
    # TODO: Port SelectSamplesForm and get_context to FastAPI
    # context = get_context(current_user, request.query_params)
    # if isinstance(lab_prep := context.get("lab_prep"), models.LabPrep):
    #     form = SelectSamplesForm(
    #         "reindex", context=context,
    #         select_libraries=True,
    #         selected_libraries=[lib for lib in lab_prep.libraries if not lib.is_indexed()]
    #     )
    # else:
    #     form = SelectSamplesForm(
    #         "reindex", context=context,
    #         select_libraries=True,
    #     )
    # return await form.make_response()
    pass