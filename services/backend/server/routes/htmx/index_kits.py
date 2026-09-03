from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession, queries as Q, categories as C, utils, models

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol, StaticSpreadsheet, TextColumn
from ...forms.actions.edit_kit_actions import EditKitBarcodesForm
from ...forms.models import IndexKitForm

router = APIRouter(prefix="/index_kits", tags=["index-kits"])

class IndexKitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(title="Index Type", label="type", col_size=2, choices=C.IndexType.as_selectable(), sortable=True, sort_by="type_id"),
        TableCol(title="Protocols", label="protocols", col_size=2),
    ]


@router.get("/render-table-page")
def render_index_kit_table(
    name: str | None = Query(None, description="Search by kit name"),
    identifier: str | None = Query(None, description="Search by kit identifier"),
    id: str | None = Query(None, description="Search by kit ID"),
    type_in: list[C.IndexType] | None = Depends(dependencies.parse_enum_ids(C.IndexType, "type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.IndexKit, default=models.IndexKit.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = IndexKitTable(route="render_index_kit_table", page=page, order_by=order_by)
    table.template = "components/tables/index_kit.html"
    stmt = Q.index_kit.select(type_in=type_in)

    if type_in:
        table.filter_values["type"] = type_in

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
        stmt = Q.index_kit.search(name=name, statement=stmt)
    elif identifier:
        table.active_search_var = "identifier"
        table.active_query_value = identifier
        stmt = Q.index_kit.search(identifier=identifier, statement=stmt)
    elif id:
        table.active_search_var = "id"
        table.active_query_value = str(id)
        try:
            stmt = Q.index_kit.select(id=int("".join(filter(str.isdigit, id))), statement=stmt)
        except ValueError:
            raise exc.BadRequestException()
        
    stmt = Q.index_kit.search(name=name, identifier=identifier, statement=stmt)
    
    index_kits, count = session.page(stmt, page=page, order_by=order_by)
    table.set_num_pages(count)
    return table.make_response(index_kits=index_kits)


@router.get("/spreadsheet/{index_kit_id}", dependencies=[Depends(dependencies.require_user_id)])
def render_index_kit_spreadsheet(
    index_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    df = session.pd.get_index_kit_barcodes(index_kit_id, per_index=True)
    df = df.drop(columns=["adapter_id"])

    columns = []
    for col in df.columns:
        if "sequence" in col:
            width = 200
        elif "well" in col:
            width = 100
        else:
            width = 150
        columns.append(TextColumn(col, col, width, max_length=1000))

    spreadsheet = StaticSpreadsheet(df, columns=columns, id=f"index_kit_table-{index_kit_id}")
    return responses.htmx_response(content=spreadsheet.render())


@router.get("/search-index_kits", dependencies=[Depends(dependencies.require_user_id)])
def search_index_kits(
    word: str = Query(..., description="Search term for kit name or identifier"),
    type: C.IndexType | None = Depends(dependencies.parse_enum_id(C.IndexType, "type")),
    type_in: list[C.IndexType] | None = Depends(dependencies.parse_enum_ids(C.IndexType, "type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    stmt = Q.index_kit.select(type=type, type_in=type_in)
    stmt = Q.index_kit.search(name=word, identifier=word, statement=stmt)
    
    kits, _ = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/index_kit.html", results=kits)


router.include_router(EditKitBarcodesForm.Router())
router.include_router(IndexKitForm.Router())

