from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import SampleStatus, LibraryStatus, PoolStatus

from ....core import dependencies, responses

router = APIRouter(prefix="/qubit_measure", tags=["qubit_measure"])


@router.get("/begin")
async def begin_qubit_measure_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(default=None),
    experiment_id: int | None = Query(default=None),
    pool_id: int | None = Query(default=None),
    entity: str | None = Query(default=None),
):
    """Begin the Qubit measurement workflow."""
    # TODO: Port SelectSamplesForm and get_context to FastAPI
    # context = get_context(request)
    # form = SelectSamplesForm(
    #     workflow="qubit_measure", context=context,
    #     sample_status_filter=[SampleStatus.STORED],
    #     library_status_filter=[LibraryStatus.PREPARING],
    #     pool_status_filter=[PoolStatus.STORED],
    #     select_lanes=True if entity is None or entity == "lane" else False,
    #     select_pools=True if entity is None or entity == "pool" else False,
    #     select_libraries=True if entity is None or entity == "library" else False,
    #     select_samples=True if entity is None or entity == "sample" else False,
    # )
    # return await form.make_response()
    pass