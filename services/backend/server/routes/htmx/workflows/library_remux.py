from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import LibraryStatus, MUXType, AccessType

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/library_remux", tags=["library_remux"])


@router.get("/begin/{library_id}")
async def begin_library_remux_workflow(
    request: Request,
    library_id: int,
    current_user: models.User = Depends(dependencies.get_user),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the library remux workflow."""
    # TODO: Port FlexReMuxForm / OligoReMuxForm to FastAPI HTMXForm
    # library = await session.first(Q.library.select(id=library_id))
    # if library is None:
    #     raise exc.NotFoundException()
    # access_type = await library.get_access_type(session, current_user)
    # if access_type < AccessType.EDIT:
    #     raise exc.NoPermissionsException()
    # if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
    #     raise exc.NoPermissionsException()
    # match library.mux_type:
    #     case MUXType.TENX_FLEX_PROBE:
    #         form = FlexReMuxForm(library=library)
    #     case MUXType.TENX_OLIGO | MUXType.TENX_ABC_HASH:
    #         form = OligoReMuxForm(library=library)
    #     case _:
    #         raise exc.BadRequestException()
    # return await form.make_response()
    pass