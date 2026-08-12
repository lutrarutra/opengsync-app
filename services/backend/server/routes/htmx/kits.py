from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc, config
from ... import forms
from ...components.tables import HTMXTable, TableCol, StaticSpreadsheet, TextColumn

router = APIRouter(prefix="/kits", tags=["kits"])

class KitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(title="Type", label="type", col_size=2, choices=C.KitType.as_selectable(), sortable=True, sort_by="kit_type_id"),
    ]

@router.get("/render-table-page")
def render_kit_table(
    name: str | None = Query(None, description="Search by kit name"),
    identifier: str | None = Query(None, description="Search by kit identifier"),
    id: str | None = Query(None, description="Search by kit ID"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    protocol_id: int | None = Query(None, description="Filter by protocol ID"),
    type_in: list[C.KitType] | None = Depends(dependencies.parse_enum_ids(C.KitType, "type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = KitTable(route="render_kit_table", page=page)
    table.template = "components/tables/kit.html"
    stmt = Q.kit.select(type_in=type_in, protocol_id=protocol_id)

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
        stmt = Q.kit.search(name=name, statement=stmt)
    elif identifier:
        table.active_search_var = "identifier"
        table.active_query_value = identifier
        stmt = Q.kit.search(identifier=identifier, statement=stmt)
    elif id:
        table.active_search_var = "id"
        table.active_query_value = str(id)
        try:
            stmt = Q.kit.select(id=int("".join(filter(str.isdigit, id))), statement=stmt)
        except ValueError:
            raise exc.BadRequestException()
        
    stmt = Q.kit.search(name=name, identifier=identifier, statement=stmt)
        
    if protocol_id is not None:
        table.template = "components/tables/protocol-kit.html"
        table.url_params["protocol_id"] = protocol_id
        table.context["protocol_id"] = protocol_id
        table.context["protocol"] = session.get_one(Q.protocol.select(id=protocol_id))
    
    kits, count = session.page(stmt, page=page)
    table.set_num_pages(count)
    return table.make_response(kits=kits)


@router.get("/index-kit-spreadsheet/{index_kit_id}", dependencies=[Depends(dependencies.require_user)])
def render_index_kit_spreadsheet(
    index_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    df = session.pd.get_index_kit_barcodes(index_kit_id, per_index=True)
    df = df.drop(columns=["adapter_id"])

    columns = []
    for i, col in enumerate(df.columns):
        if "sequence" in col:
            width = 200
        elif "well" in col:
            width = 100
        else:
            width = 150
        columns.append(TextColumn(col, col, width, max_length=1000))

    spreadsheet = StaticSpreadsheet(df, columns=columns, id=f"index_kit_table-{index_kit_id}")
    return responses.htmx_response(content=spreadsheet.render())


@router.get("/search-kits", dependencies=[Depends(dependencies.require_user)])
def search_kits(
    word: str = Query(..., description="Search term for kit name or identifier"),
    kit_type: C.KitType | None = Depends(dependencies.parse_enum_id(C.KitType, "kit_type")),
    kit_type_in: list[C.KitType] | None = Depends(dependencies.parse_enum_ids(C.KitType, "kit_type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    stmt = Q.kit.select(type=kit_type, type_in=kit_type_in)
    stmt = Q.kit.search(name=word, identifier=word, statement=stmt)
    
    kits, count = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/kit.html", results=kits)


@router.get("/search-index_kits", dependencies=[Depends(dependencies.require_user)])
def search_index_kits(
    word: str = Query(..., description="Search term for kit name or identifier"),
    type: C.IndexType | None = Depends(dependencies.parse_enum_id(C.IndexType, "type")),
    type_in: list[C.IndexType] | None = Depends(dependencies.parse_enum_ids(C.IndexType, "type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    stmt = Q.index_kit.select(type=type, type_in=type_in)
    stmt = Q.index_kit.search(name=word, identifier=word, statement=stmt)
    
    kits, count = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/index_kit.html", results=kits)


router.include_router(forms.models.FeatureKitForm.Router())
router.include_router(forms.actions.EditKitFeaturesAction.Router())
router.include_router(forms.actions.QueryBarcodeSequencesAction.Router())
router.include_router(forms.actions.BarcodeConstraintsAction.Router())
router.include_router(forms.models.IndexKitForm.Router())
router.include_router(forms.models.KitForm.Router())