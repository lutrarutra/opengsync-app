from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession
from opengsync_db.categories import MUXType

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/mux_prep", tags=["mux_prep"])


@router.get("/begin/{lab_prep_id}/{mux_type_id}")
async def begin_mux_prep_workflow(
    request: Request,
    lab_prep_id: int,
    mux_type_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Begin the multiplexing prep workflow."""
    # TODO: Port OligoMuxForm / FlexMuxForm / OCMMuxForm to FastAPI HTMXForm
    # mux_type = MUXType.get(mux_type_id)
    # if mux_type is None:
    #     raise exc.BadRequestException()
    # lab_prep = await session.first(Q.lab_prep.select(id=lab_prep_id))
    # if lab_prep is None:
    #     raise exc.NotFoundException()
    # if mux_type == MUXType.TENX_OLIGO:
    #     form = OligoMuxForm(lab_prep=lab_prep)
    # elif mux_type == MUXType.TENX_FLEX_PROBE:
    #     form = FlexMuxForm(lab_prep=lab_prep)
    # elif mux_type == MUXType.TENX_ON_CHIP:
    #     form = OCMMuxForm(lab_prep=lab_prep)
    # else:
    #     raise NotImplementedError(f"Multiplexing type {mux_type} is not implemented.")
    # return await form.make_response()
    pass