from contextlib import suppress

import pandas as pd
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils, actions

from ...core import dependencies, responses, exceptions as exc
from ...utils import parsing
from ... import forms
from ...components.tables import HTMXTable, TableCol, TextColumn, StaticSpreadsheet

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

    libraries = table.paginate(
        session,
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
    return table.make_response(libraries=libraries)


@router.get("/search")
def search_libraries(
    word: str | None = Query(None, description="Search word for library name"),
    selected_id: int | None = Query(None, description="Currently selected library"),
    current_user: models.User = Depends(dependencies.require_user),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.library.select()

    if selected_id is not None and not word:
        stmt = Q.library.select(id=selected_id, statement=stmt)
    elif word:
        stmt = Q.library.search(name=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Library.name.asc())

    if not current_user.is_insider:
        stmt = Q.library.select(viewer_id=current_user.id, statement=stmt)

    libraries, _ = session.page(stmt, page=page)
    return responses.htmx_response(template="components/search/library.html", libraries=libraries)


@router.get("/{library_id}/reads", dependencies=[Depends(dependencies.library_permissions)])
def render_library_reads(
    library_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    library = session.get_one(Q.library.select(id=library_id))

    if not library.read_qualities:
        raise exc.BadRequestException("No read quality data available for this library.")
    
    library_stats_per_lane = session.pd.get_library_stats(library_id, per_lane=True)
    library_stats_average = session.pd.get_library_stats(library_id, per_lane=False)

    per_lane_columns = []
    for col in library_stats_per_lane.columns:
        per_lane_columns.append(TextColumn(col, col.replace("_", " ").title(), {"lane": 50}.get(col, 150), max_length=1000))

    average_columns = []
    for col in library_stats_average.columns:
        average_columns.append(TextColumn(col, col.replace("_", " ").title(), {"lane": 50}.get(col, 150), max_length=1000))

    per_lane_stats_ss = StaticSpreadsheet(df=library_stats_per_lane, columns=per_lane_columns, id=f"library-{library_id}-reads-per-lane")
    average_stats_ss = StaticSpreadsheet(df=library_stats_average, columns=average_columns, id=f"library-{library_id}-reads-average")
    
    return responses.htmx_response(
        "components/library-reads.html", library=library,
        per_lane_stats_ss=per_lane_stats_ss, average_stats_ss=average_stats_ss
    )


@router.get("/render-feed", dependencies=[Depends(dependencies.require_insider)])
def render_prep_feed(
    session: SyncSession = Depends(dependencies.db_session),
):
    df = session.pd.query(
        sa.select(
            models.Library.id,
            models.Library.service_type_id.label("service_type"),
            models.Library.name.label("library_name"),
            models.Library.status_id.label("status"),
        ).where(
            models.Library.status_id.in_([
                C.LibraryStatus.ACCEPTED,
                C.LibraryStatus.PREPARING,
                C.LibraryStatus.STORED,
            ]),
        )
    )
    return responses.htmx_response("components/dashboard/preps-feed.html", df=df)


@router.get("/render-feed/{service_type_id}", dependencies=[Depends(dependencies.require_insider)])
def render_prep_feed_detail(
    service_type_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    try:
        service_type = C.ServiceType.get(service_type_id)
    except ValueError:
        raise exc.BadRequestException()

    df = session.pd.query(
        sa.select(
            models.Library.id,
            models.Library.seq_request_id,
            models.Library.service_type_id.label("service_type"),
            models.Library.name.label("library_name"),
            models.Library.status_id.label("status"),
        ).where(
            models.Library.status_id.in_([
                C.LibraryStatus.ACCEPTED,
                C.LibraryStatus.PREPARING,
                C.LibraryStatus.STORED,
            ]),
            models.Library.service_type_id == service_type.id,
        ).order_by(models.Library.seq_request_id, models.Library.id)
    )

    data: dict[str, list] = {
        "seq_request": [],
        "num_waiting_samples": [],
        "num_preparing_libraries": [],
        "num_pooled_libraries": [],
        "library_type_counts": [],
        "num_waiting_libraries": [],
        "num_waiting_pools": [],
    }

    class SeqRequestIdKey(BaseModel):
        seq_request_id: int
        
    for key, _ in parsing.safe_groupby(df, "seq_request_id", SeqRequestIdKey, dropna=True):
        seq_request = session.get_one(
            Q.seq_request.select(id=key.seq_request_id),
            options=[
                orm.selectinload(models.SeqRequest.samples),
                orm.selectinload(models.SeqRequest.libraries),
                orm.selectinload(models.SeqRequest.pools),
                orm.selectinload(models.SeqRequest.assignees),
                orm.selectinload(models.SeqRequest.requestor),
            ],
        )

        data["seq_request"].append(seq_request)
        data["num_waiting_samples"].append(sum(
            s.status == C.SampleStatus.WAITING_DELIVERY for s in seq_request.samples
        ))
        data["num_preparing_libraries"].append(sum(
            ls.status == C.LibraryStatus.PREPARING for ls in seq_request.libraries
        ))
        data["num_pooled_libraries"].append(sum(
            ls.status in [
                C.LibraryStatus.POOLED,
                C.LibraryStatus.SEQUENCED,
                C.LibraryStatus.SHARED,
                C.LibraryStatus.ARCHIVED,
            ]
            for ls in seq_request.libraries
        ))
        data["library_type_counts"].append(seq_request.library_type_counts)
        data["num_waiting_libraries"].append(sum(
            ls.status == C.LibraryStatus.ACCEPTED for ls in seq_request.libraries
        ))
        data["num_waiting_pools"].append(sum(
            p.status == C.PoolStatus.ACCEPTED for p in seq_request.pools
        ))

    return responses.htmx_response(
        "components/dashboard/preps-feed-detail.html",
        service_type=service_type,
        df=pd.DataFrame(data),
    )


@router.delete("/{library_id}/remove-sample")
def remove_sample_from_library(
    library_id: int,
    sample_id: int = Query(..., description="The ID of the sample to remove from the library"),
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.library_permissions),
):
    if access_level < C.AccessLevel.WRITE:
        raise exc.NoPermissionsException("You do not have permission to remove samples from this library.")
    sample = session.get_one(Q.sample.select(id=sample_id))
    actions.unlink_sample_library(session=session, sample_id=sample_id, library_id=library_id)
    return responses.htmx_response(
        redirect=responses.url_for("library_page", library_id=library_id),
        flash=responses.flash(f"Sample {sample.name} removed from library.", "success")
    )


@router.get("/{library_id}/crispr-guides", dependencies=[Depends(dependencies.library_permissions)])
def render_library_table_crispr_guides(
    library_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    library = session.get_one(Q.library.select(id=library_id))
    if library.type != C.LibraryType.PARSE_SC_CRISPR:
        raise exc.BadRequestException("Library is not a Parse CRISPR library.")

    cols = ["guide_name", "target_gene", "prefix", "guide_sequence", "suffix"]
    guides = (library.properties or {}).get("crispr_guides") or []
    df = pd.DataFrame(guides)
    for col in cols:
        if col not in df.columns:
            df[col] = None
    df: pd.DataFrame = df[cols]  # type: ignore

    columns: list = [
        TextColumn(col, col.replace("_", " ").title(), 200, max_length=1000)
        for col in df.columns
    ]
    spreadsheet = StaticSpreadsheet(df, columns=columns, id=f"library-crispr-guides-{library_id}")
    return responses.htmx_response(content=spreadsheet.render())


@router.get("/{library_id}/mux-table", dependencies=[Depends(dependencies.library_permissions)])
def render_library_table_mux_table(
    library_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    library = session.get_one(
        Q.library.select(id=library_id),
        options=[orm.selectinload(models.Library.sample_links)],
    )
    if library.mux_type is None:
        raise exc.BadRequestException("Library is not multiplexed.")

    mux_data: dict[str, list] = {
        "sample_name": [],
        "barcode": [],
    }
    oligo = library.mux_type == C.MUXType.TENX_OLIGO
    if oligo:
        mux_data["read"] = []
        mux_data["pattern"] = []

    for link in library.sample_links:
        mux_data["sample_name"].append(link.sample.name)
        if link.mux is not None:
            mux_data["barcode"].append(link.mux.get("barcode"))
            if oligo:
                mux_data["read"].append(link.mux.get("read", ""))
                mux_data["pattern"].append(link.mux.get("pattern", ""))
        else:
            mux_data["barcode"].append(None)
            if oligo:
                mux_data["read"].append("")
                mux_data["pattern"].append("")

    df = pd.DataFrame(mux_data)
    widths = {"sample_name": 300, "barcode": 200, "read": 80, "pattern": 200}
    columns: list = [
        TextColumn(
            col,
            col.replace("_", " ").title().replace("Id", "ID").replace("Cmo", "CMO"),
            widths.get(col, 100),
            max_length=1000,
        ) for col in df.columns
    ]
    spreadsheet = StaticSpreadsheet(df, columns=columns, id=f"library-mux-table-{library_id}")
    return responses.htmx_response(content=spreadsheet.render())


router.include_router(forms.models.LibraryForm.Router())
router.include_router(forms.actions.LibraryFeaturesAction.Router())