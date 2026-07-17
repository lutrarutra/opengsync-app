from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import orm
import sqlalchemy as sa

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, exceptions as exc
from ... import forms
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/protocols", tags=["protocols"])
router.include_router(forms.actions.AddKitsToProtocolAction.Router())
router.include_router(forms.models.ProtocolForm.Router())

class ProtocolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Read Structure", label="read_structure", col_size=3),
        TableCol(title="Assay", label="service_type", col_size=2, choices=C.ServiceType.as_selectable(), sortable=True, sort_by="service_type_id"),
    ]


@router.get("/render-table-page")
def render_protocol_table(
    name: str | None = Query(None, description="Search by protocol name"),
    id: str | None = Query(None, description="Search by protocol ID"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    service_type_in: list[C.ServiceType] | None = Depends(dependencies.parse_enum_ids(C.ServiceType, "service_type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = ProtocolTable(route="render_protocol_table", page=page)
    table.template = "components/tables/protocol.html"
    stmt = Q.protocol.select(service_type_in=service_type_in)

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
    elif id:
        table.active_search_var = "id"
        table.active_query_value = str(id)
        try:
            stmt = Q.protocol.select(id=int("".join(filter(str.isdigit, id))), statement=stmt)
        except ValueError:
            raise exc.BadRequestException()
    
    stmt = Q.protocol.search(name=name, statement=stmt)
    protocols, count = session.page(stmt, page=page)
    table.set_num_pages(count)
    return table.make_response(protocols=protocols)


@router.delete("/{protocol_id}/delete", dependencies=[Depends(dependencies.require_admin), Depends(dependencies.audit_log)])
def delete_protocol(
    protocol_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    protocol = session.get_one(Q.protocol.select(id=protocol_id))
    session.delete(protocol)
    return responses.htmx_response(
        redirect=responses.url_for("protocols_page"),
        flash=responses.flash("Protocol deleted!", "success"),
    )

@router.delete("/{protocol_id}/remove-kit", dependencies=[Depends(dependencies.require_insider), Depends(dependencies.audit_log)])
def remove_kit_from_protocol(
    protocol_id: int,
    kit_id: int = Query(..., description="ID of the kit to remove from the protocol"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    protocol = session.get_one(Q.protocol.select(id=protocol_id).options(orm.selectinload(models.Protocol.kit_links)))
        
    kit = session.get_one(Q.kit.select(id=kit_id))

    for link in protocol.kit_links:
        if link.kit_id == kit_id:
            protocol.kit_links.remove(link)

    session.save(protocol)

    return responses.htmx_response(
        flash=responses.flash(f"Kit '{kit.name}' removed from protocol '{protocol.name}'.", "success"),
        redirect=responses.url_for("protocols_page"),
    )

@router.delete("/{protocol_id}/remove-kit-combination", dependencies=[Depends(dependencies.require_insider), Depends(dependencies.audit_log)])
def remove_kit_combination_from_protocol(
    protocol_id: int,
    kit_id: int = Query(..., description="ID of the kit to remove from the protocol"),
    combination_num: int = Query(..., description="Combination number of the kit to remove from the protocol"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    protocol = session.get_one(Q.protocol.select(id=protocol_id))
        
    link = session.get_one(sa.Select(models.links.ProtocolKitLink).where(
        models.links.ProtocolKitLink.protocol_id == protocol_id,
        models.links.ProtocolKitLink.kit_id == kit_id,
        models.links.ProtocolKitLink.combination_num == combination_num
    ))

    protocol.kit_links.remove(link)

    session.save(protocol)

    return responses.htmx_response(
        flash=responses.flash(f"Kit combination '{link.combination_num}' removed from protocol '{protocol.name}'.", "success"),
        redirect=responses.url_for("protocols_page"),
    )