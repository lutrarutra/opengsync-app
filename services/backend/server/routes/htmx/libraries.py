from contextlib import suppress

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ... import forms
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/libraries", tags=["libraries"])


class LibraryTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(
            title="Name", label="name", col_size=3, searchable=True, sortable=True
        ),
        TableCol(
            title="Pool",
            label="pool_name",
            col_size=1,
            searchable=True,
            sortable=True,
            sort_by="pool_id",
        ),
        TableCol(
            title="Library Type",
            label="type",
            col_size=1,
            choices=C.LibraryType.as_selectable(),
        ),
        TableCol(
            title="Status",
            label="status",
            col_size=1,
            sortable=True,
            sort_by="status_id",
            choices=C.LibraryStatus.as_selectable(),
        ),
        TableCol(title="Request", label="seq_request", col_size=2),
        TableCol(title="Owner", label="owner", col_size=1),
    ]


@router.get("/render-table-page")
def render_library_table(
    pool_id: int | None = Query(None, description="Filter libraries by pool ID"),
    experiment_id: int | None = Query(None, description="Filter libraries by experiment ID"),
    lab_prep_id: int | None = Query(None, description="Filter libraries by lab prep ID"),
    seq_request_id: int | None = Query(None, description="Filter libraries by seq request ID"),
    sample_id: int | None = Query(None, description="Filter libraries by sample ID"),
    name: str | None = Query(None, description="Search by library name"),
    pool_name: str | None = Query(None, description="Search by pool name"),
    id_search: str | None = Query(None, alias="id", description="Search by library ID"),
    browse: str | None = Query(None, description="Browse context for library selection component"),
    type_in: list[C.LibraryType] | None = Depends(
        dependencies.parse_enum_ids(enum_type=C.LibraryType, query_param="type_in")
    ),
    status_in: list[C.LibraryStatus] | None = Depends(
        dependencies.parse_enum_ids(enum_type=C.LibraryStatus, query_param="status_in")
    ),
    indexed: bool | None = Query(None, description="Filter libraries by whether they are indexed"),
    pooled: bool | None = Query(None, description="Filter libraries by whether they are pooled"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    current_user: models.User = Depends(dependencies.require_user),
    order_by: utils.OrderBy | None = Depends(
        dependencies.parse_order_by(
            model=models.Library, default=models.Library.id.desc()
        )
    ),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = LibraryTable(route="render_library_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    if type_in:
        table.filter_values["type"] = type_in

    stmt = Q.library.select(
        pool_id=pool_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
        seq_request_id=seq_request_id,
        sample_id=sample_id,
        status_in=status_in,
        type_in=type_in,
        indexed=indexed,
        pooled=pooled,
    )

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
    elif pool_name:
        table.active_search_var = "pool_name"
        table.active_query_value = pool_name
    elif id_search:
        table.active_search_var = "id"
        table.active_query_value = id_search
        with suppress(ValueError):
            stmt = Q.library.select(id=int("".join(filter(str.isdigit, id_search))), statement=stmt)

    stmt = Q.library.search(name=name, pool_name=pool_name, statement=stmt)

    if pool_id is not None:
        if session.get_access_level(Q.pool.permissions(pool_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this pool.")
        table.template = "components/tables/pool-library.html"
        table.url_params["pool_id"] = pool_id
        table.context["pool"] = session.get_one(Q.pool.select(id=pool_id))
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this experiment.")
        table.template = "components/tables/experiment-library.html"
        table.url_params["experiment_id"] = experiment_id
        table.context["experiment_id"] = experiment_id
    elif lab_prep_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this lab prep.")
        table.template = "components/tables/lab_prep-library.html"
        table.url_params["lab_prep_id"] = lab_prep_id
        table.context["lab_prep"] = session.get_one(Q.lab_prep.select(id=lab_prep_id))
    elif seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this seq request.")
        table.template = "components/tables/seq_request-library.html"
        table.url_params["seq_request_id"] = seq_request_id
        table.context["seq_request"] = session.get_one(Q.seq_request.select(id=seq_request_id))
    elif sample_id is not None:
        if session.get_access_level(Q.sample.permissions(sample_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this sample.")
        table.template = "components/tables/sample-library.html"
        table.url_params["sample_id"] = sample_id
        table.context["sample_id"] = sample_id
    else:
        table.template = "components/tables/library.html"
        if not current_user.is_insider:
            stmt = Q.library.select(viewer_id=current_user.id, statement=stmt)

    if browse is not None:
        table.template = "components/tables/browse-library.html"
        table.context["browse_context"] = browse
        table.url_params["browse"] = browse

    libraries, count = session.page(
        stmt,
        page=page,
        order_by=order_by,
        options=[
            orm.selectinload(models.Library.pool),
            orm.selectinload(models.Library.seq_request),
            orm.selectinload(models.Library.owner),
            orm.selectinload(models.Library.indices),
        ],
    )
    table.set_num_pages(count)
    return table.make_response(libraries=libraries)


@router.get("/properties")
def render_library_properties(
    seq_request_id: int | None = Query(None, description="Seq request ID to filter libraries"),
    project_id: int | None = Query(None, description="Project ID to filter libraries"),
    library_id: int | None = Query(None, description="Library ID to edit properties for"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    if seq_request_id is None and project_id is None and library_id is None:
        raise exc.BadRequestException("Must provide at least one of seq_request_id, project_id, or library_id")
    
    access_level = C.AccessLevel.NONE
    if seq_request_id is not None:
        if (access_level := session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this seq request.")
    elif project_id is not None:
        if (access_level := session.get_access_level(Q.project.permissions(project_id, current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this project.")
    elif library_id is not None:
        if (access_level := session.get_access_level(Q.library.permissions(library_id, current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this library.")
        
    libraries = session.get_all(Q.library.select(seq_request_id=seq_request_id, project_id=project_id, id=library_id).order_by(models.Library.id.asc()))

    form = forms.LibraryPropertyForm(
        access_level=access_level, libraries=libraries,
        seq_request_id=seq_request_id, project_id=project_id, library_id=library_id
    )
    return form.make_response()

@router.post("/properties")
def edit_library_properties(response = Depends(forms.LibraryPropertyForm.edit)): return response