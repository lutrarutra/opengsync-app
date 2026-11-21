
import pandas as pd
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, responses, exceptions as exc, query_options
from ...utils import parsing
from ... import forms
from .data_browser import DataScope, data_browser_router
from ...components.tables import (
    Table, TableState, Col, Field, Text, Exact, Enum, Entity, Variant, related, TextColumn, StaticSpreadsheet,
)

router = APIRouter(prefix="/libraries", tags=["libraries"])


L = models.Library
_FULL_NAME = Q.search.full_name(models.User)
_PROJECT_PATH = (L.sample_links, models.links.SampleLibraryLink.sample, models.Sample.project)
_GROUP_PATH = (L.seq_request, models.SeqRequest.group)


class LibraryTable(Table):
    key = "lib"
    model = models.Library
    noun = "libraries"
    load = (
        orm.selectinload(L.pool),
        orm.selectinload(L.seq_request),
        orm.selectinload(L.owner),
        orm.selectinload(L.indices),
    )
    columns = [
        Col("id", "ID", sort=True, search=Exact(L.id), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(L.name, L.sample_name, compact=True), hideable=False, size=4),
        Col(
            "pool", "Pool", size=1,
            sort=related(L.pool, models.Pool.name),
            search=Text(models.Pool.name, via=L.pool),
            filter=Entity(models.Pool, via=L.pool, option=query_options.pool_option, search=(models.Pool.name,)),
        ),
        Col("type", "Type", sort=True, filter=Enum(C.LibraryType), size=1),
        Col("status", "Status", sort=True, filter=Enum(C.LibraryStatus), size=1),
        Col(
            "seq_request", "Request", size=2,
            sort=related(L.seq_request, models.SeqRequest.name),
            search=Text(models.SeqRequest.name, via=L.seq_request),
            filter=Entity(
                models.SeqRequest, via=L.seq_request, option=query_options.seq_request_option,
                search=(models.SeqRequest.name,),
            ),
        ),
        Col(
            "owner", "Owner", size=1,
            sort=related(L.owner, _FULL_NAME),
            search=Text(_FULL_NAME, models.User.email, via=L.owner, weight=0.9),
            filter=Entity(models.User, via=L.owner, option=query_options.user_option, search=(_FULL_NAME, models.User.email)),
        ),
        Col(
            "index", "Index", size=3, index_toggle=True,
            search=Text(
                models.LibraryIndex.name_i7, models.LibraryIndex.name_i5,
                models.LibraryIndex.sequence_i7, models.LibraryIndex.sequence_i5, via=L.indices,
            ),
        ),
        Col("index_type", "Index Type", sort=True, filter=Enum(C.IndexType), size=2),
        Col(
            "barcode_orientation", "Barcode Orientation", sort=True, size=2,
            # Validated reverse complements are stored reverse-complemented as FORWARD, so REVERSE_COMPLEMENT never occurs
            filter=Enum(
                C.BarcodeOrientation, nullable=True,
                choices=[o for o in C.BarcodeOrientation.as_list() if o is not C.BarcodeOrientation.REVERSE_COMPLEMENT],
            ),
        ),
        Col("qubit_concentration", "Qubit Conc.", sort=True, size=2),
        Col("avg_fragment_size", "Avg. Fragment Size", sort=True, size=2),
        Field(
            "project", "Project",
            search=Text(models.Project.title, models.Project.identifier, via=_PROJECT_PATH),
            filter=Entity(
                models.Project, via=_PROJECT_PATH, option=query_options.project_option,
                search=(models.Project.title, models.Project.identifier),
            ),
        ),
        Field(
            "group", "Group",
            search=Text(models.Group.name, via=_GROUP_PATH),
            filter=Entity(models.Group, via=_GROUP_PATH, option=query_options.group_option, search=(models.Group.name,)),
        ),
    ]
    _browse = dict(row_template="components/tables/rows/browse-library.html", dom_id="select-libraries-table", url_state=False)
    variants = {
        "default": Variant(
            ["id", "name", "pool", "type", "status", "seq_request", "index"], "components/tables/rows/library.html",
            dom_id="library-table",
        ),
        "pool": Variant(
            ["id", "name", "type", "seq_request", "index"], "components/tables/rows/pool-library.html",
            dom_id="pool-library-table", actions=True,
        ),
        "experiment": Variant(
            ["id", "name", "type", "pool", "index"], "components/tables/rows/experiment-library.html",
            dom_id="experiment-library-table",
        ),
        "lab_prep": Variant(
            ["id", "name", "type", "status", "pool", "seq_request", "index"], "components/tables/rows/lab_prep-library.html",
            dom_id="lab_prep-library-table", actions=True,
        ),
        "seq_request": Variant(
            ["id", "name", "pool", "type", "status", "index"], "components/tables/rows/seq_request-library.html",
            dom_id="seq_request-library-table", actions=True, toolbar="components/tables/toolbars/seq_request-library.html",
        ),
        "sample": Variant(
            ["id", "name", "type", "status", "seq_request", "index"], "components/tables/rows/sample-library.html",
            dom_id="sample-library-table",
        ),
        "browse": Variant(["id", "name", "type", "status"], **_browse),
        "browse-qubit-measure": Variant(["id", "name", "type", "status", "qubit_concentration"], **_browse),
        "browse-ba-report": Variant(["id", "name", "type", "status", "avg_fragment_size"], **_browse),
        "browse-index-check": Variant(["id", "name", "type", "status", "index_type", "barcode_orientation"], **_browse),
    }


@router.get("/render-table-page")
def render_library_table(
    pool_id: int | None = Query(None, description="Filter libraries by pool ID"),
    experiment_id: int | None = Query(None, description="Filter libraries by experiment ID"),
    lab_prep_id: int | None = Query(None, description="Filter libraries by lab prep ID"),
    seq_request_id: int | None = Query(None, description="Filter libraries by seq request ID"),
    sample_id: int | None = Query(None, description="Filter libraries by sample ID"),
    browse: str | None = Query(None, description="Browse context for library selection component"),
    indexed: bool | None = Query(None, description="Filter libraries by whether they are indexed"),
    pooled: bool | None = Query(None, description="Filter libraries by whether they are pooled"),
    state: TableState = Depends(LibraryTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.library.select(
        pool_id=pool_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
        seq_request_id=seq_request_id,
        sample_id=sample_id,
        indexed=indexed,
        pooled=pooled,
    )
    table = LibraryTable(state, route="render_library_table", user=current_user)
    table.url_params.update({k: v for k, v in {"indexed": indexed, "pooled": pooled}.items() if v is not None})

    if pool_id is not None:
        if session.get_access_level(Q.pool.permissions(pool_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this pool.")
        table.use("pool", pool_id=pool_id, pool=session.get_one(Q.pool.select(id=pool_id)))
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this experiment.")
        table.use("experiment", experiment_id=experiment_id)
        table.context["experiment_id"] = experiment_id
    elif lab_prep_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this lab prep.")
        table.use("lab_prep", lab_prep_id=lab_prep_id, lab_prep=session.get_one(Q.lab_prep.select(id=lab_prep_id)))
    elif seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this seq request.")
        table.use(
            "seq_request", seq_request_id=seq_request_id,
            seq_request=session.get_one(Q.seq_request.select(id=seq_request_id)),
        )
    elif sample_id is not None:
        if session.get_access_level(Q.sample.permissions(sample_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view libraries for this sample.")
        table.use("sample", sample_id=sample_id)
        table.context["sample_id"] = sample_id
    elif not current_user.is_insider:
        stmt = Q.library.select(viewer_id=current_user.id, statement=stmt)

    if browse is not None:
        table.use(f"browse-{browse}" if f"browse-{browse}" in LibraryTable.variants else "browse", browse=browse)
        table.context["browse_context"] = browse

    return table.render(session, stmt)


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

    return query_options.search_response(
        session, stmt, page=page, option=query_options.library_option,
        load=[orm.selectinload(models.Library.seq_request)],
    )


@router.get("/{library_id}/reads", dependencies=[Depends(dependencies.library_permissions)])
def render_library_reads(
    library_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    library = session.get_one(Q.library.select(id=library_id))

    if not library.read_qualities:
        raise exc.BadRequestException("No read quality data available for this library.")
    
    library_stats_per_lane = T.library_stats(
        session.get_pandas(Q.pd.library_stats(library_id), limit=None),
        per_lane=True,
        expand_qc_=True,
        weighted_average=True,
    )
    library_stats_average = T.library_stats(
        session.get_pandas(Q.pd.library_stats(library_id), limit=None),
        per_lane=False,
        expand_qc_=True,
        weighted_average=True,
    )

    per_lane_columns = []
    for col in library_stats_per_lane.columns:
        per_lane_columns.append(TextColumn(col, col.replace("_", " ").title(), {"lane": 50}.get(col, 150), max_length=1000))

    average_columns = []
    for col in library_stats_average.columns:
        average_columns.append(TextColumn(col, col.replace("_", " ").title(), {"lane": 50}.get(col, 150), max_length=1000))

    per_lane_stats_ss = StaticSpreadsheet(df=library_stats_per_lane, columns=per_lane_columns, id=f"library-{library_id}-reads-per-lane")
    average_stats_ss = StaticSpreadsheet(df=library_stats_average, columns=average_columns, id=f"library-{library_id}-reads-average")
    
    return responses.htmx_response(
        template="components/library-reads.html", library=library,
        per_lane_stats_ss=per_lane_stats_ss, average_stats_ss=average_stats_ss
    )


@router.get("/render-feed", dependencies=[Depends(dependencies.require_insider)])
def render_prep_feed(
    session: SyncSession = Depends(dependencies.db_session),
):
    df = session.get_pandas(
        sa.select(
            models.Library.id,
            models.Library.service_type.label("service_type"),
            models.Library.name.label("library_name"),
            models.Library.status.label("status"),
        ).where(
            models.Library.status.in_([
                C.LibraryStatus.ACCEPTED,
                C.LibraryStatus.PREPARING,
                C.LibraryStatus.STORED,
            ]),
        ),
        limit=None,
    )
    return responses.htmx_response(template="components/dashboard/preps-feed.html", df=df)


@router.get("/render-feed/{service_type_id}", dependencies=[Depends(dependencies.require_insider)])
def render_prep_feed_detail(
    service_type_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    try:
        service_type = C.ServiceType.get(service_type_id)
    except ValueError:
        raise exc.BadRequestException()

    df = session.get_pandas(
        sa.select(
            models.Library.id,
            models.Library.seq_request_id,
            models.Library.service_type.label("service_type"),
            models.Library.name.label("library_name"),
            models.Library.status.label("status"),
        ).where(
            models.Library.status.in_([
                C.LibraryStatus.ACCEPTED,
                C.LibraryStatus.PREPARING,
                C.LibraryStatus.STORED,
            ]),
            models.Library.service_type == service_type,
        ).order_by(models.Library.seq_request_id, models.Library.id),
        limit=None,
    )

    data: dict[str, list] = {
        "seq_request": [],
        "num_waiting_samples": [],
        "num_preparing_libraries": [],
        "num_stored_libraries": [],
        "library_status_counts": [],
        "library_type_counts": [],
        "num_waiting_libraries": [],
        "num_waiting_pools": [],
    }

    class SeqRequestIdKey(BaseModel):
        seq_request_id: int
        
    for key, _ in parsing.safe_groupby(df, SeqRequestIdKey, dropna=True):
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
        data["num_stored_libraries"].append(sum(
            ls.status == C.LibraryStatus.STORED for ls in seq_request.libraries
        ))
        status_counts: dict[C.LibraryStatus, int] = {}
        for ls in seq_request.libraries:
            status_counts[ls.status] = status_counts.get(ls.status, 0) + 1
        data["library_status_counts"].append(dict(sorted(status_counts.items(), key=lambda x: x[0].id)))
        data["library_type_counts"].append(seq_request.library_type_counts)
        data["num_waiting_libraries"].append(sum(
            ls.status == C.LibraryStatus.ACCEPTED for ls in seq_request.libraries
        ))
        data["num_waiting_pools"].append(sum(
            p.status == C.PoolStatus.ACCEPTED for p in seq_request.pools
        ))

    return responses.htmx_response(
        template="components/dashboard/preps-feed-detail.html",
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
router.include_router(data_browser_router(DataScope(
    entity="library", label="library", permissions=dependencies.library_permissions,
    page_route="library_page", tab="library-data_paths-tab",
)))
