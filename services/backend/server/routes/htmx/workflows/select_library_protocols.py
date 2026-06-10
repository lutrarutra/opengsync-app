from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/select_library_protocols", tags=["select_library_protocols"])


@router.get("/begin/{lab_prep_id}")
async def begin_select_library_protocols_workflow(
    request: Request,
    lab_prep_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the select library protocols workflow."""
    # TODO: Port LibraryProtocolSelectForm to FastAPI HTMXForm
    # lab_prep = await session.first(Q.lab_prep.select(id=lab_prep_id))
    # if lab_prep is None:
    #     raise exc.NotFoundException()
    # if lab_prep.prep_file is None:
    #     data = {"library_id": [], "protocol_id": []}
    #     for library in lab_prep.libraries:
    #         data["library_id"].append(library.id)
    #         data["protocol_id"].append(library.protocol_id)
    #     library_table = pd.DataFrame(data)
    #     form = LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=None, library_table=library_table)
    # else:
    #     # ... read from file
    #     form = LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=None, library_table=df)
    # return await form.make_response()
    pass