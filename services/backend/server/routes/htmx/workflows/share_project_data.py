from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import PoolStatus

from ....core import dependencies, responses

router = APIRouter(prefix="/share-project-data", tags=["share_project_data"])


@router.get("/begin")
async def begin_share_project_data_workflow(
    request: Request,
    project_id: int | None = Query(..., ),
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    pass