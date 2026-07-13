from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ...core.context import ctx
from ... import forms


router = APIRouter(prefix="/pools", tags=["pools"])


class PoolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=1, sort_by="status_id", sortable=True, choices=C.PoolStatus.as_selectable()),
        TableCol(title="Type", label="type", col_size=1, sort_by="type_id", sortable=True, choices=C.PoolType.as_selectable()),
        TableCol(title="Owner", label="owner", col_size=2, searchable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
    ]


@router.get("/render-table-page")
def render_pool_table(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter pools"),
    status_in: list[C.PoolStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.PoolStatus, query_param="status_in")),
    library_types_in: list[C.LibraryType] | None = Depends(dependencies.parse_enum_ids(enum_type=C.LibraryType, query_param="library_types_in")),
    type_in: list[C.PoolType] | None = Depends(dependencies.parse_enum_ids(enum_type=C.PoolType, query_param="type_in")),
    browse: str | None = Query(None, description="Browse context for pool selection component"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Pool, default=models.Pool.id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = PoolTable(route="render_pool_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    if library_types_in:
        table.filter_values["library_types"] = library_types_in
    if type_in:
        table.filter_values["type"] = type_in

    stmt = Q.pool.select(
        seq_request_id=seq_request_id,
        status_in=status_in,
        library_types_in=library_types_in,
        type_in=type_in,
    )

    if seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.template = "components/tables/seq_request-pool.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request_id"] = seq_request_id
    elif browse is not None:
        table.template = "components/tables/browse-pool.html"
        table.context["browse_context"] = browse
        table.url_params["browse"] = browse
    else:
        table.template = "components/tables/pool.html"
        if not current_user.is_insider():
            stmt = Q.pool.select(viewer_id=current_user.id, statement=stmt)

    pools, count = session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Pool.owner),
            orm.with_expression(models.Pool._num_libraries, models.Pool.num_libraries.expression),
            orm.with_expression(models.Pool._library_types, models.Pool.library_types.expression),
        ]
    )
    table.set_num_pages(count)

    return table.make_response(pools=pools)


@router.get("/create")
def render_create_pool_form(
    request: Request,
):
    """Render the create pool form."""
    form = forms.models.PoolForm(request, form_type="create")
    return form.make_response()


@router.post("/create")
def create_pool(response = Depends(forms.models.PoolForm.create)): return response


@router.get("/{pool_id}/edit")
def render_pool_edit_form(
    pool_id: int,
    request: Request,
    access_level: C.AccessLevel = Depends(dependencies.pool_permissions),
    session: SyncSession = Depends(dependencies.db_session)
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to edit this pool.")

    pool = session.get_one(Q.pool.select(id=pool_id).options(
        orm.selectinload(models.Pool.contact),
    ))

    form = forms.models.PoolForm(request, form_type="edit", pool=pool)
    return form.make_response()


@router.post("/{pool_id}/edit")
def edit_pool(response = Depends(forms.models.PoolForm.edit)): return response


@router.get("/{pool_id}/clone")
def render_pool_clone_form(
    pool_id: int,
    request: Request,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session)
):
    pool = session.get_one(Q.pool.select(id=pool_id).options(
        orm.selectinload(models.Pool.contact),
        orm.selectinload(models.Pool.libraries),
        orm.selectinload(models.Pool.dilutions),
    ))

    form = forms.models.PoolForm(request, form_type="clone", pool=pool)
    return form.make_response()


@router.post("/{pool_id}/clone")
def clone_pool(response = Depends(forms.models.PoolForm.clone)): return response


@router.get("/search")
def search_pools(
    word: str | None = Query(None, description="Search word for pool name"),
    selected_id: int | None = Query(None, description="Currently selected pool"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.pool.select()

    if selected_id is not None and not word:
        stmt = Q.pool.select(id=selected_id, statement=stmt)
    elif word is not None:
        stmt = Q.pool.search(name=word, statement=stmt)

    if not current_user.is_insider():
        stmt = Q.pool.select(viewer_id=current_user.id, statement=stmt)

    pools, count = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/pool.html", pools=pools)
