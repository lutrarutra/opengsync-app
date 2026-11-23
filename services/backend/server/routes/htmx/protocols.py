from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import orm
import sqlalchemy as sa

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses, query_options
from ... import forms
from ...components.tables import Table, TableState, Col, Text, Exact, Enum, Variant

router = APIRouter(prefix="/protocols", tags=["protocols"])

PR = models.Protocol


class ProtocolTable(Table):
    key = "prot"
    model = models.Protocol
    noun = "protocols"
    columns = [
        Col("id", "ID", sort=True, search=Exact(PR.id), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(PR.name, compact=True), hideable=False, size=6),
        Col("service_type", "Assay", sort=True, filter=Enum(C.ServiceType), size=3),
        Col("read_structure", "Read Structure", search=Text(PR.read_structure), size=4),
    ]
    variants = {
        "default": Variant(["id", "name", "service_type", "read_structure"], "components/tables/rows/protocol.html", dom_id="protocol-table"),
    }


@router.get("/render-table-page")
def render_protocol_table(
    state: TableState = Depends(ProtocolTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = ProtocolTable(state, route="render_protocol_table", user=current_user)
    return table.render(session, Q.protocol.select())


@router.get("/query")
def query_protocols(
    word: str | None = Query(None, description="Search word for protocol name"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    service_type_in: list[C.ServiceType] | None = Depends(dependencies.parse_enum_ids(C.ServiceType, "service_type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    """Options for a spreadsheet QueryColumn. Protocols are visible to every user."""
    return query_options.options_response(
        session, Q.protocol.select(service_type_in=service_type_in), columns=query_options.PROTOCOL_SEARCH_COLUMNS,
        word=word, page=page, order_column=models.Protocol.name, label=lambda protocol: protocol.name,
    )


@router.delete("/{protocol_id}/delete", dependencies=[Depends(dependencies.require_admin)])
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

@router.delete("/{protocol_id}/remove-kit", dependencies=[Depends(dependencies.require_insider)])
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
        # redirect=responses.url_for("protocols_page"),
    )

@router.delete("/{protocol_id}/remove-kit-combination", dependencies=[Depends(dependencies.require_insider)])
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
        # redirect=responses.url_for("protocols_page"),
    )

router.include_router(forms.actions.AddKitsToProtocolAction.Router())
router.include_router(forms.models.ProtocolForm.Router())