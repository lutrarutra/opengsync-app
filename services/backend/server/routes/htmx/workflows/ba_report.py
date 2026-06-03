from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import LibraryStatus, PoolStatus

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/ba_report", tags=["ba_report"])


@router.get("/begin")
async def begin_ba_report_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(default=None),
    experiment_id: int | None = Query(default=None),
    pool_id: int | None = Query(default=None),
    lab_prep_id: int | None = Query(default=None),
    entity: str | None = Query(default=None),
):
    """Begin the BioAnalyzer report workflow."""
    # TODO: Port SelectSamplesForm and get_context to FastAPI
    # context = get_context(request)
    # form = SelectSamplesForm(
    #     workflow="ba_report", context=context,
    #     library_status_filter=[LibraryStatus.PREPARING],
    #     pool_status_filter=[PoolStatus.STORED],
    #     select_libraries=True if entity is None or entity == "library" else False,
    #     select_pools=True if not context.get("lab_prep") and (entity is None or entity == "pool") else False,
    #     select_lanes=True if not context.get("lab_prep") and (entity is None or entity == "lane") else False,
    # )
    # return await form.make_response()
    pass