from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession
from opengsync_db.categories import LibraryStatus

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/select_pool_libraries", tags=["select_pool_libraries"])


@router.get("/begin/{pool_id}")
def begin_select_pool_libraries_workflow(
    request: Request,
    pool_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the select pool libraries workflow."""
    # TODO: Port SelectSamplesForm to FastAPI HTMXForm
    # pool = session.first(Q.pool.select(id=pool_id))
    # if pool is None:
    #     raise exc.NotFoundException()
    # form = SelectSamplesForm(
    #     "select_pool_libraries",
    #     select_libraries=True,
    #     context={"pool": pool},
    #     library_status_filter=[
    #         LibraryStatus.DRAFT, LibraryStatus.SUBMITTED,
    #         LibraryStatus.ACCEPTED, LibraryStatus.PREPARING,
    #         LibraryStatus.STORED,
    #     ],
    # )
    # return form.make_response()
    pass