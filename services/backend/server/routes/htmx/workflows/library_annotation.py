from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import AccessType

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/library_annotation", tags=["library_annotation"])


@router.get("/begin/{seq_request_id}")
async def begin_library_annotation_workflow(
    request: Request,
    seq_request_id: int,
    current_user: models.User = Depends(dependencies.get_user),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the library annotation workflow."""
    # TODO: Port ProjectSelectForm to FastAPI HTMXForm
    # seq_request = await session.first(Q.seq_request.select(id=seq_request_id))
    # if seq_request is None:
    #     raise exc.NotFoundException()
    # access_type = await seq_request.get_access_type(session, current_user)
    # if access_type < AccessType.EDIT:
    #     raise exc.NoPermissionsException()
    # form = ProjectSelectForm(seq_request=seq_request)
    # return await form.make_response()
    pass