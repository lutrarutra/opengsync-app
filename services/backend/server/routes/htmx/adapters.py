from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies
from ...components.tables import Table, TableState, Col, Field, Text, Exact, Variant

router = APIRouter(prefix="/adapters", tags=["adapters"])


A = models.Adapter
_ROW = "components/tables/rows/index_kit-adapter.html"
_DOM = "index_kit-adapter-table"


class AdapterTable(Table):
    key = "adapt"
    model = models.Adapter
    noun = "adapters"
    load = (orm.selectinload(A.barcodes_i7), orm.selectinload(A.barcodes_i5))
    columns = [
        Col("id", "ID", sort=True, search=Exact(A.id), hideable=False, size=1),
        Col("well", "Well", sort=True, search=Text(A.well), size=1),
        Col("name", "Name", sort=True, size=2),
        Col("name_i7", "Name i7", size=2),
        Col("sequence_i7", "Sequence i7", size=2),
        Col("name_i5", "Name i5", size=2),
        Col("sequence_i5", "Sequence i5", size=2),
        Col("sequence_1", "Sequence 1", size=2),
        Col("sequence_2", "Sequence 2", size=2),
        Col("sequence_3", "Sequence 3", size=2),
        Col("sequence_4", "Sequence 4", size=2),
        Field("barcode", "Barcode", search=Text(models.Barcode.name, models.Barcode.sequence, via=A.barcodes_i7)),
        Field("barcode_i5", "Barcode i5", search=Text(models.Barcode.name, models.Barcode.sequence, via=A.barcodes_i5)),
    ]
    # the columns follow the index kit's type (the row template branches the same way)
    variants = {
        "default": Variant(["id", "well", "name_i7", "sequence_i7", "name_i5", "sequence_i5"], _ROW, dom_id=_DOM),
        "single": Variant(["id", "well", "name_i7", "sequence_i7"], _ROW, dom_id=_DOM),
        "combinatorial": Variant(["id", "name_i7", "sequence_i7", "name_i5", "sequence_i5"], _ROW, dom_id=_DOM),
        "atac": Variant(["id", "well", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], _ROW, dom_id=_DOM),
    }


@router.get("/render-table-page")
def render_adapter_table(
    index_kit_id: int = Query(..., description="Filter by index kit ID"),
    state: TableState = Depends(AdapterTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    index_kit = session.get_one(Q.index_kit.select(id=index_kit_id))
    variant = {
        C.IndexType.SINGLE_INDEX_I7: "single",
        C.IndexType.COMBINATORIAL_DUAL_INDEX: "combinatorial",
        C.IndexType.TENX_ATAC_INDEX: "atac",
    }.get(index_kit.type, "default")
    table = AdapterTable(state, route="render_adapter_table", user=current_user)
    table.use(variant, index_kit_id=index_kit_id, index_kit=index_kit)
    return table.render(session, Q.adapter.select(index_kit_id=index_kit_id))
