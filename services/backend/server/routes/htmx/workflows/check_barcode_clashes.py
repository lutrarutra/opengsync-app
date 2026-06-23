from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from ....core import dependencies, responses, exceptions as exc
from ....forms.workflows import CheckBarcodeClashesForm

router = APIRouter(prefix="/check_barcode_clashes", tags=["check_barcode_clashes"])


def _build_seq_request_barcode_data(seq_request: models.SeqRequest) -> pd.DataFrame:
    """Build a barcode DataFrame from a seq request's pools and their libraries."""
    library_data = {
        "library_id": [],
        "library_name": [],
        "pool": [],
        "pool_id": [],
        "sequence_i7": [],
        "sequence_i5": [],
        "kit_i7_id": [],
        "kit_i5_id": [],
        "index_type_id": [],
    }

    for pool in seq_request.pools:
        for library in pool.libraries:
            for index in library.indices:
                library_data["library_id"].append(library.id)
                library_data["library_name"].append(library.name)
                library_data["pool"].append(pool.name)
                library_data["pool_id"].append(pool.id)
                library_data["sequence_i7"].append(index.sequence_i7)
                library_data["sequence_i5"].append(index.sequence_i5)
                library_data["kit_i7_id"].append(index.index_kit_i7_id)
                library_data["kit_i5_id"].append(index.index_kit_i5_id)
                library_data["index_type_id"].append(index.type.id)

    return pd.DataFrame(library_data)


@router.get("/begin")
async def begin_check_barcode_clashes_workflow(
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
    seq_request_id: int | None = Query(None),
    experiment_id: int | None = Query(None),
):
    """Begin the check barcode clashes workflow.

    If ``seq_request_id`` is given, directly checks barcode clashes for
    all libraries in that sequencing request's pools.
    If ``experiment_id`` is given, checks barcode clashes across all
    lanes in that experiment.
    Otherwise returns a generic message (no pre-selected data).
    """
    if seq_request_id is not None:
        if await session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        seq_request = await session.get_one(
            Q.seq_request.select(id=seq_request_id).options(
                orm.selectinload(models.SeqRequest.pools)
                .selectinload(models.Pool.libraries)
                .selectinload(models.Library.indices),
            )
        )

        library_df = _build_seq_request_barcode_data(seq_request)
        form = CheckBarcodeClashesForm(request, library_df, groupby="pool")
        return await form.make_response()

    if experiment_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        barcode_df = await session.pd.get_experiment_barcodes(experiment_id)
        form = CheckBarcodeClashesForm(request, barcode_df, groupby="lane")
        return await form.make_response()

    # No specific context — render a simple "select a seq request" message
    return await responses.htmx_response(
        template="workflows/check_barcode_clashes/clashes-1.html",
        df=pd.DataFrame(),
        groupby=None,
        warn_user=False,
        form=None,
    )


@router.get("/check-seq-request")
async def check_seq_request_barcode_clashes(
    request: Request,
    seq_request_id: int = Query(...),
    current_user: models.User = Depends(dependencies.require_user),
    access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Check barcode clashes for a specific sequencing request."""
    if access_level < C.AccessLevel.READ:
        raise exc.NoPermissionsException()

    seq_request = await session.get_one(
        Q.seq_request.select(id=seq_request_id).options(
            orm.selectinload(models.SeqRequest.pools)
            .selectinload(models.Pool.libraries)
            .selectinload(models.Library.indices),
        )
    )

    library_df = _build_seq_request_barcode_data(seq_request)
    form = CheckBarcodeClashesForm(request, library_df, groupby="pool")
    return await form.make_response()


@router.get("/check-experiment")
async def check_experiment_barcode_clashes(
    request: Request,
    experiment_id: int = Query(...),
    current_user: models.User = Depends(dependencies.require_insider),
    session: AsyncSession = Depends(dependencies.db_session),
):
    """Check barcode clashes for a specific experiment."""
    barcode_df = await session.pd.get_experiment_barcodes(experiment_id)
    form = CheckBarcodeClashesForm(request, barcode_df, groupby="lane")
    return await form.make_response()
