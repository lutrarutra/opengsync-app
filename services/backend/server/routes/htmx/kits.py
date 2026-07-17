from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc, config
from ... import forms
from ...components.tables import HTMXTable, TableCol

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