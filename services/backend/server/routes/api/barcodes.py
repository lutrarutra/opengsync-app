from typing import Any
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
import pandas as pd

from opengsync_db import models, SyncSession

from ...core import dependencies

router = APIRouter(prefix="/barcodes", tags=["api", "barcodes"])


class QueryBarcodeSequenceRequest(BaseModel):
    sequence: str
    limit: int = Field(default=5, ge=1)


def _barcode_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = json.loads(df.to_json(orient="records"))
    for row in records:
        type_id = row.get("type_id")
        row["type"] = {"id": int(type_id)} if type_id is not None else None
    return records


@router.post("/query-barcode-sequence", dependencies=[Depends(dependencies.require_insider)])
def query_barcode_sequence(
    body: QueryBarcodeSequenceRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    sequence = body.sequence.upper()
    fc_df = session.pd.query_barcode_sequences(sequence, limit=body.limit)
    rc_df = session.pd.query_barcode_sequences(models.Barcode.reverse_complement(sequence), limit=body.limit)

    return {
        "fc_results": _barcode_records(fc_df),
        "rc_results": _barcode_records(rc_df),
    }
