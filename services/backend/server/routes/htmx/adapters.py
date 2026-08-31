from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import models, SyncSession, queries as Q, utils

from ...core import dependencies, exceptions as exc
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/adapters", tags=["adapters"])


class AdapterTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Well", label="well", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, sortable=True),
        TableCol(title="Name i7", label="name_i7", col_size=2),
        TableCol(title="Name i5", label="name_i5", col_size=2),
        TableCol(title="Sequence i7", label="sequence_i7", col_size=2),
        TableCol(title="Sequence i5", label="sequence_i5", col_size=2),
        TableCol(title="Sequence 1", label="sequence_1", col_size=2),
        TableCol(title="Sequence 2", label="sequence_2", col_size=2),
        TableCol(title="Sequence 3", label="sequence_3", col_size=2),
        TableCol(title="Sequence 4", label="sequence_4", col_size=2),
    ]


@router.get("/render-table-page")
def render_adapter_table(
    index_kit_id: int = Query(..., description="Filter by index kit ID"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Adapter, default=models.Adapter.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = AdapterTable(route="render_adapter_table", page=page, order_by=order_by)
    stmt = Q.adapter.select(index_kit_id=index_kit_id)

    if index_kit_id is not None:
        table.template = "components/tables/index_kit-adapter.html"
        table.context["index_kit"] = session.get_one(Q.index_kit.select(id=index_kit_id))
        table.url_params["index_kit_id"] = index_kit_id
    else:
        raise exc.BadRequestException("index_kit_id must be provided.")

    adapters = table.paginate(
        session,
        stmt,
        page=page,
        order_by=order_by,
    )
    return table.make_response(adapters=adapters)