from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import orm
from opengsync_db import SyncSession, models
from opengsync_db import categories as C
from opengsync_db import queries as Q

from ... import forms
from ...components.tables import (
    Table, TableState, Col, Text, Exact, Enum, Variant,
)
from ...core import dependencies, responses, query_options

router = APIRouter(prefix="/kits", tags=["kits"])


K = models.Kit


class KitTable(Table):
    key = "kit"
    model = models.Kit
    noun = "kits"
    load = (orm.selectinload(K.protocol_links),)
    columns = [
        Col("id", "ID", sort=True, search=Exact(K.id), hideable=False, size=1),
        Col("identifier", "Identifier", sort=True, search=Text(K.identifier, compact=True), size=2),
        Col("name", "Name", sort=True, search=Text(K.name), hideable=False, size=3),
        Col("combinations", "Combinations", size=2),
        Col("type", "Type", sort=K.kit_type, filter=Enum(C.KitType, column=K.kit_type), size=2),
    ]
    variants = {
        "default": Variant(["id", "identifier", "name", "type"], "components/tables/rows/kit.html", dom_id="kit-table"),
        "protocol": Variant(
            ["id", "identifier", "name", "combinations", "type"], "components/tables/rows/protocol-kit.html",
            dom_id="protocol-kit-table", actions=True,
        ),
    }


@router.get("/render-table-page")
def render_kit_table(
    protocol_id: int | None = Query(None, description="Filter by protocol ID"),
    state: TableState = Depends(KitTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    stmt = Q.kit.select(protocol_id=protocol_id)
    table = KitTable(state, route="render_kit_table", user=current_user)

    if protocol_id is not None:
        table.use("protocol", protocol_id=protocol_id, protocol=session.get_one(Q.protocol.select(id=protocol_id)))
        table.context["protocol_id"] = protocol_id

    return table.render(session, stmt)


@router.get("/search-kits", dependencies=[Depends(dependencies.require_user_id)])
def search_kits(
    word: str | None = Query(None, description="Search term for kit name or identifier"),
    kit_type: C.KitType | None = Depends(dependencies.parse_enum_id(C.KitType, "kit_type")),
    kit_type_in: list[C.KitType] | None = Depends(dependencies.parse_enum_ids(C.KitType, "kit_type_in")),
    selected_id: int | None = Query(None, description="Currently selected kit"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    stmt = Q.kit.select(type=kit_type, type_in=kit_type_in)
    if selected_id is not None and not word:
        stmt = Q.kit.select(id=selected_id, statement=stmt)
    elif word:
        stmt = Q.kit.search(name=word, identifier=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Kit.name.asc())

    return query_options.search_response(session, stmt, page=page, option=query_options.kit_option)


@router.get("/query")
def query_kits(
    word: str | None = Query(None, description="Search word for kit name or identifier"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    type_in: list[C.KitType] | None = Depends(dependencies.parse_enum_ids(C.KitType, "type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    """Options for a spreadsheet QueryColumn: kits of every type. Kits are visible to every user."""
    return query_options.options_response(
        session, Q.kit.select(type_in=type_in), columns=query_options.KIT_SEARCH_COLUMNS,
        word=word, page=page, order_column=models.Kit.name, label=query_options.kit_label,
    )


@router.delete("/delete", dependencies=[Depends(dependencies.require_admin)])
def delete_kit(
    kit_id: int = Query(..., description="ID of the kit to delete"),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    kit = session.get_one(Q.kit.select(id=kit_id))
    session.delete(kit, flush=True)
    return responses.htmx_response(
        redirect=responses.url_for("kits_page"), flash=responses.flash("Kit deleted successfully.", "success")
    )


router.include_router(forms.actions.EditKitFeaturesAction.Router())
router.include_router(forms.actions.QueryBarcodeSequencesAction.Router())
router.include_router(forms.actions.BarcodeConstraintsAction.Router())
router.include_router(forms.models.KitForm.Router())
