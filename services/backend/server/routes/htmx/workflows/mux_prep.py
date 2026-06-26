from fastapi import APIRouter, Depends, Request

from opengsync_db import models, AsyncSession, queries as Q
from opengsync_db.categories import MUXType

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/mux_prep", tags=["mux_prep"])


@router.get("/{lab_prep_id}/begin/{mux_type_id}")
async def begin_mux_prep_workflow(
    request: Request,
    lab_prep_id: int,
    mux_type_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
):
    
    if not (mux_type := MUXType.get(mux_type_id)):
        raise exc.BadRequestException()
    
    lab_prep = await session.get_one(Q.lab_prep.select(id=lab_prep_id))
    
    # if mux_type == MUXType.TENX_OLIGO:
    #     form = forms.OligoMuxForm(lab_prep=lab_prep)
    # elif mux_type == MUXType.TENX_FLEX_PROBE:
    #     form = forms.FlexMuxForm(lab_prep=lab_prep)
    # elif mux_type == MUXType.TENX_ON_CHIP:
    #     form = forms.OCMMuxForm(lab_prep=lab_prep)
    # else:
    #     raise NotImplementedError(f"Multiplexing type {mux_type} is not implemented.")



@router.get("/{lab_prep_id}/sample-pooling")
async def mux_sample_pooling(
    lab_prep_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
):
    pass