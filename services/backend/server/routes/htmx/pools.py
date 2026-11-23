from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions
from opengsync_db.transitions import run_operation, lab as lab_ops

from ...core import dependencies, responses, exceptions as exc, query_options
from ...components.tables import Table, TableState, Col, Field, Text, Exact, Enum, Entity, Variant, related
from ...forms.models import PoolForm


router = APIRouter(prefix="/pools", tags=["pools"])


P = models.Pool
_FULL_NAME = Q.search.full_name(models.User)


class PoolTable(Table):
    key = "pool"
    model = models.Pool
    noun = "pools"
    load = (
        orm.selectinload(P.owner),
        orm.selectinload(P.lane_links),
        orm.with_expression(P._num_libraries, P.num_libraries.expression),
        orm.with_expression(P._library_types, P.library_types.expression),
    )
    columns = [
        Col("id", "ID", sort=True, search=Exact(P.id, prefixes=("P",)), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(P.name, compact=True), hideable=False, size=4),
        Col("lanes", "Lanes", size=2.5),
        Col("library_types", "Library Types", size=3.5, filter=Enum(C.LibraryType, column=models.Library.type, via=P.libraries)),
        Col("status", "Status", sort=True, filter=Enum(C.PoolStatus), size=3),
        Col("type", "Type", sort=True, filter=Enum(C.PoolType), size=2),
        Col(
            "owner", "Owner", size=3.5,
            sort=related(P.owner, _FULL_NAME),
            search=Text(_FULL_NAME, models.User.email, via=P.owner, weight=0.9),
            filter=Entity(models.User, via=P.owner, option=query_options.user_option, search=(_FULL_NAME, models.User.email)),
        ),
        Col("num_libraries", "# Libraries", sort=True, size=1),
        Col("num_m_reads_requested", "# Reads Requested", sort=True, size=1),
        Col("reads", "# Reads", size=1),
        Col("molarity", "Molarity", size=1),
        Col("qubit_concentration", "Qubit Conc.", sort=True, size=2),
        Col("avg_fragment_size", "Avg. Fragment Size", sort=True, size=2),
        Field(
            "seq_request", "Request",
            search=Text(models.SeqRequest.name, via=P.seq_request),
            filter=Entity(
                models.SeqRequest, via=P.seq_request, option=query_options.seq_request_option,
                search=(models.SeqRequest.name,),
            ),
        ),
        Field(
            "experiment", "Experiment",
            search=Text(models.Experiment.name, via=P.experiment),
            filter=Entity(
                models.Experiment, via=P.experiment, option=query_options.experiment_option,
                search=(models.Experiment.name,),
            ),
        ),
    ]
    _browse = dict(row_template="components/tables/rows/browse-pool.html", dom_id="select-pools-table", url_state=False)
    variants = {
        "default": Variant(
            ["id", "name", "library_types", "status", "type", "owner", "num_libraries"], "components/tables/rows/pool.html",
            dom_id="pool-table",
        ),
        "seq_request": Variant(
            ["id", "name", "library_types", "status", "owner", "num_libraries", "num_m_reads_requested"],
            "components/tables/rows/seq_request-pool.html", dom_id="seq_request-pool-table",
        ),
        "lab_prep": Variant(
            ["id", "name", "library_types", "status", "owner", "num_libraries"], "components/tables/rows/lab_prep-pool.html",
            dom_id="lab_prep-pool-table",
        ),
        "experiment": Variant(
            ["id", "name", "lanes", "library_types", "status", "reads", "molarity", "num_libraries"],
            "components/tables/rows/experiment-pool.html", dom_id="experiment-pool-table", actions=True,
            prelude="components/tables/rows/experiment-pool-prelude.html",
        ),
        "browse": Variant(["id", "name", "library_types", "status", "num_libraries"], **_browse),
        "browse-qubit-measure": Variant(["id", "name", "library_types", "status", "qubit_concentration", "num_libraries"], **_browse),
        "browse-ba-report": Variant(["id", "name", "library_types", "status", "avg_fragment_size", "num_libraries"], **_browse),
    }


@router.get("/render-table-page")
def render_pool_table(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter pools"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter pools"),
    lab_prep_id: int | None = Query(None, description="Optional lab prep ID to filter pools"),
    browse: str | None = Query(None, description="Browse context for pool selection component"),
    state: TableState = Depends(PoolTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.pool.select(
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        lab_prep_id=lab_prep_id,
    )
    table = PoolTable(state, route="render_pool_table", user=current_user)

    if seq_request_id is not None:
        if session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        table.use("seq_request", seq_request_id=seq_request_id)
        table.context["seq_request_id"] = seq_request_id
    elif lab_prep_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view pools for this lab prep.")
        table.use("lab_prep", lab_prep_id=lab_prep_id)
        table.context["lab_prep_id"] = lab_prep_id
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view pools for this experiment.")
        experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
            orm.selectinload(models.Experiment.lanes).selectinload(models.Lane.pool_links),
        ))
        table.use("experiment", experiment_id=experiment_id, experiment=experiment)
        table.context["can_edit_pooling"] = (experiment.status == C.ExperimentStatus.DRAFT or current_user.is_admin) and not experiment.workflow.combined_lanes
    elif not current_user.is_insider:
        stmt = Q.pool.select(viewer_id=current_user.id, statement=stmt)

    if browse is not None:
        if browse == "select-experiment-pools":
            stmt = Q.pool.select(associated_to_experiment=False, statement=stmt)
        table.use(f"browse-{browse}" if f"browse-{browse}" in PoolTable.variants else "browse", browse=browse)
        table.context["browse_context"] = browse

    return table.render(session, stmt)


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
    elif word:
        stmt = Q.pool.search(name=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Pool.name.asc())

    if not current_user.is_insider:
        stmt = Q.pool.select(viewer_id=current_user.id, statement=stmt)

    return query_options.search_response(session, stmt, page=page, option=query_options.pool_option)


@router.delete("/{pool_id}/remove-library/{library_id}")
def remove_library_from_pool(
    pool_id: int,
    library_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider)
):
    pool = session.get_one(Q.pool.select(id=pool_id).options(
        orm.selectinload(models.Pool.libraries),
    ))

    library = session.get_one(Q.library.select(id=library_id))

    if pool.status != C.PoolStatus.DRAFT and not current_user.is_admin:
        raise exc.NoPermissionsException()

    if library.pool_id != pool.id:
        raise exc.NotFoundException(f"Library {library.name} is not in pool {pool.name}")

    with run_operation(session, lab_ops.REMOVE_POOL_LIBRARY, subject=pool):
        actions.set_library_pool(session, library, None)
        if library.status == C.LibraryStatus.POOLED:
            library.status = C.LibraryStatus.STORED

        session.save(pool)
    return responses.htmx_response(
        # redirect=responses.url_for("pool_page", pool_id=pool_id),
        flash=responses.flash(f"Library {library.name} removed from pool", "success")
    )


@router.delete("/{pool_id}/remove-libraries")
def remove_libraries_from_pool(
    pool_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    pool = session.get_one(Q.pool.select(id=pool_id).options(
        orm.selectinload(models.Pool.libraries),
    ))

    if pool.status != C.PoolStatus.DRAFT and not current_user.is_admin:
        raise exc.NoPermissionsException()

    with run_operation(session, lab_ops.REMOVE_POOL_LIBRARY, subject=pool):
        for library in list(pool.libraries):
            actions.set_library_pool(session, library, None)
            if library.status == C.LibraryStatus.POOLED:
                library.status = C.LibraryStatus.STORED

        session.save(pool)
    
    return responses.htmx_response(
        redirect=responses.url_for("pool_page", pool_id=pool_id),
        flash=responses.flash("Libraries removed from pool", "success")
    )


@router.delete("/{pool_id}/delete", dependencies=[Depends(dependencies.require_insider)])
def delete_pool(
    pool_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    pool = session.get_one(Q.pool.select(id=pool_id).options(
        orm.with_expression(models.Pool._num_libraries, models.Pool.num_libraries.expression)
    ))

    if pool.num_libraries > 0:
        raise exc.NoPermissionsException("Cannot delete a pool that has libraries.")

    session.delete(pool)
    
    return responses.htmx_response(
        redirect=responses.url_for("pools_page"),
        flash=responses.flash("Pool deleted", "success")
    )


@router.get("/render-plate/{plate_id}", dependencies=[Depends(dependencies.require_insider)])
def render_plate_tab(
    plate_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    plate = session.get_one(
        Q.plate.select(id=plate_id).options(
            orm.selectinload(models.Plate.sample_links),
        )
    )
    pool = session.scalar(Q.pool.select().where(models.Pool.plate_id == plate_id))
    return responses.htmx_response(template="components/plate.html", plate=plate, pool=pool)


@router.get("/render-feed", dependencies=[Depends(dependencies.require_insider)])
def render_pool_feed(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    PAGE_LIMIT = 10
    pools, total = session.page(
        Q.pool.select(status_in=[C.PoolStatus.STORED, C.PoolStatus.ACCEPTED]),
        page=page,
        limit=PAGE_LIMIT,
        order_by=models.Pool.id.desc(),
        options=[
            orm.selectinload(models.Pool.owner),
            orm.selectinload(models.Pool.experiment),
        ],
    )
    return responses.htmx_response(
        template="components/dashboard/pools-feed.html",
        pools=pools,
        current_page=page,
        limit=PAGE_LIMIT,
        total=total,
    )


router.include_router(PoolForm.Router())