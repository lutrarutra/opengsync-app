from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/library_pooling", tags=["library_pooling"])


@router.get("/begin/{lab_prep_id}")
async def begin_library_pooling_workflow(
    request: Request,
    lab_prep_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the library pooling workflow."""
    # TODO: Port LibraryPoolingForm to FastAPI HTMXForm
    # lab_prep = await session.first(Q.lab_prep.select(id=lab_prep_id))
    # if lab_prep is None:
    #     raise exc.NotFoundException()
    # form = LibraryPoolingForm(lab_prep=lab_prep, uuid=None, formdata=None)
    # return await form.make_response()
    pass