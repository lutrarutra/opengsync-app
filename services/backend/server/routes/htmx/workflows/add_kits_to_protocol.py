from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/add_kits_to_protocol", tags=["add_kits_to_protocol"])


@router.get("/begin/{protocol_id}")
def begin_add_kits_to_protocol_workflow(
    request: Request,
    protocol_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the add kits to protocol workflow."""
    # TODO: Port AddKitCombinationsFrom to FastAPI HTMXForm
    # protocol = session.first(Q.protocol.select(id=protocol_id))
    # if protocol is None:
    #     raise exc.NotFoundException()
    # form = AddKitCombinationsFrom(formdata=await request.form(), protocol=protocol)
    # return form.make_response()
    pass