from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession, queries as Q
from opengsync_db.categories import MUXType

from ....core import dependencies, responses, exceptions as exc
from ....forms.workflows.mux_prep import PrepOligoMuxForm

router = APIRouter(prefix="/mux_prep", tags=["mux_prep"])


@router.get("/{lab_prep_id}/begin/{mux_type_id}")
def begin_mux_prep_workflow(
    request: Request,
    lab_prep_id: int,
    mux_type_id: int,
    uuid: str | None = None,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    if not (mux_type := MUXType.get(mux_type_id)):
        raise exc.BadRequestException()

    lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))

    if mux_type == MUXType.TENX_OLIGO:
        form = PrepOligoMuxForm(
            request=request,
            lab_prep=lab_prep,
            uuid=uuid,
        )
        return form.make_response()
    else:
        raise exc.BadRequestException(detail=f"Multiplexing type {mux_type} is not implemented.")


@router.post("/{lab_prep_id}/oligo_mux")
def parse_oligo_mux_reference(
    request: Request,
    lab_prep_id: int,
    uuid: str,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))

    form = PrepOligoMuxForm(
        request=request,
        lab_prep=lab_prep,
        uuid=uuid,
    )
    return form.process_request()


@router.get("/{lab_prep_id}/sample-pooling")
def mux_sample_pooling(
    lab_prep_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    pass