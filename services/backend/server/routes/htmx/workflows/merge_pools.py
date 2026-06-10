from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import PoolStatus

from ....core import dependencies, responses

router = APIRouter(prefix="/merge_pools", tags=["merge_pools"])


@router.get("/begin")
async def begin_merge_pools_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(default=None),
    lab_prep_id: int | None = Query(default=None),
):
    """Begin the merge pools workflow."""
    # TODO: Port SelectSamplesForm and get_context to FastAPI
    # context = get_context(current_user, request.query_params)
    # form = SelectSamplesForm(
    #     "merge_pools",
    #     context=context,
    #     select_pools=True,
    #     pool_status_filter=[
    #         PoolStatus.DRAFT, PoolStatus.SUBMITTED, PoolStatus.ACCEPTED,
    #         PoolStatus.STORED, PoolStatus.PREPARING,
    #     ],
    # )
    # return await form.make_response()
    pass