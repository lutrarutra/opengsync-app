from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession, queries as Q, categories as C, models

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, responses, query_options
from ...components.tables import (
    Table, TableState, Col, Text, Exact, Enum, Variant, StaticSpreadsheet, TextColumn,
)
from ...forms.actions.edit_kit_actions import EditKitBarcodesForm
from ...forms.models import IndexKitForm

router = APIRouter(prefix="/index_kits", tags=["index-kits"])

IK = models.IndexKit


class IndexKitTable(Table):
    key = "ikit"
    model = models.IndexKit
    noun = "index kits"
    columns = [
        Col("id", "ID", sort=True, search=Exact(IK.id), hideable=False, size=1),
        Col("identifier", "Identifier", sort=True, search=Text(IK.identifier, compact=True), size=2),
        Col("name", "Name", sort=True, search=Text(IK.name), hideable=False, size=3),
        Col("type", "Index Type", sort=True, filter=Enum(C.IndexType), size=2),
        Col("protocols", "Protocols", size=2),
    ]
    variants = {
        "default": Variant(
            ["id", "identifier", "name", "type", "protocols"], "components/tables/rows/index_kit.html",
            dom_id="index_kit-table",
        ),
    }


@router.get("/render-table-page")
def render_index_kit_table(
    state: TableState = Depends(IndexKitTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = IndexKitTable(state, route="render_index_kit_table", user=current_user)
    return table.render(session, Q.index_kit.select())


@router.get("/spreadsheet/{index_kit_id}", dependencies=[Depends(dependencies.require_user_id)])
def render_index_kit_spreadsheet(
    index_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    df = T.index_kit_barcodes(
        session.get_pandas(Q.pd.index_kit_barcodes(index_kit_id), limit=None),
        per_adapter=False,
        per_index=True,
    )
    index_kit = session.get_one(Q.index_kit.select(id=index_kit_id))
    df = T.index_kit_barcodes_per_index(df, index_kit.type)
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
    word: str | None = Query(None, description="Search term for kit name or identifier"),
    type: C.IndexType | None = Depends(dependencies.parse_enum_id(C.IndexType, "type")),
    type_in: list[C.IndexType] | None = Depends(dependencies.parse_enum_ids(C.IndexType, "type_in")),
    selected_id: int | None = Query(None, description="Currently selected kit"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    stmt = Q.index_kit.select(type=type, type_in=type_in)
    if selected_id is not None and not word:
        stmt = Q.index_kit.select(id=selected_id, statement=stmt)
    elif word:
        stmt = Q.index_kit.search(name=word, identifier=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.IndexKit.name.asc())

    return query_options.search_response(session, stmt, page=page, option=query_options.kit_option)


@router.get("/query")
def query_index_kits(
    word: str | None = Query(None, description="Search word for kit name or identifier"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    type_in: list[C.IndexType] | None = Depends(dependencies.parse_enum_ids(C.IndexType, "type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    """Options for a spreadsheet QueryColumn. Index kits are visible to every user."""
    return query_options.options_response(
        session, Q.index_kit.select(type_in=type_in), columns=query_options.KIT_SEARCH_COLUMNS,
        word=word, page=page, order_column=models.IndexKit.name, label=query_options.kit_label,
    )


router.include_router(EditKitBarcodesForm.Router())
router.include_router(IndexKitForm.Router())

