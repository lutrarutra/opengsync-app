from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from opengsync_db import SyncSession, models, utils
from opengsync_db import categories as C
from opengsync_db import queries as Q

from ... import forms
from ...components.tables import HTMXTable, TableCol
from ...core import dependencies, responses, query_options
from ...core import exceptions as exc

router = APIRouter(prefix="/kits", tags=["kits"])


class KitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(
            title="Type",
            label="type",
            col_size=2,
            choices=C.KitType.as_selectable(),
            sortable=True,
            sort_by="kit_type",
        ),
    ]


@router.get("/render-table-page")
def render_kit_table(
    id: str | None = Query(None, description="Search by kit ID"),
    name: str | None = Query(None, description="Search by kit name"),
    identifier: str | None = Query(None, description="Search by kit identifier"),
    protocol_id: int | None = Query(None, description="Filter by protocol ID"),
    type_in: list[C.KitType] | None = Depends(dependencies.parse_enum_ids(C.KitType, "type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(
        dependencies.parse_order_by(model=models.Kit, default=models.Kit.id.desc())
    ),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = KitTable(route="render_kit_table", page=page, order_by=order_by)
    table.template = "components/tables/kit.html"
    stmt = Q.kit.select(type_in=type_in, protocol_id=protocol_id)

    if type_in is not None:
        table.filter_values["type"] = type_in

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

    kits = table.paginate(session, stmt, page=page, order_by=order_by)
    return table.make_response(kits=kits)


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
