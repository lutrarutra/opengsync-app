import os

import pandas as pd
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils, actions

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import config, dependencies, overview, responses, exceptions as exc, query_options, checklists
from ...components.tables import HTMXTable, TableCol
from ... import forms
from .data_browser import DataScope, data_browser_router, experiment_data_permissions

router = APIRouter(prefix="/experiments", tags=["experiments"])


class ExperimentTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, searchable=True, sortable=True),
        TableCol(title="Workflow", label="workflow", col_size=2, choices=C.ExperimentWorkFlow.as_selectable(), sortable=True, sort_by="workflow"),
        TableCol(title="Status", label="status", col_size=2, choices=C.ExperimentStatus.as_selectable(), sortable=True, sort_by="status"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Operator", label="operator", col_size=2, searchable=True),
        TableCol(title="Created", label="timestamp_created", col_size=2, sortable=True, sort_by="timestamp_created_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


@router.get("/render-table-page")
def render_experiment_table(
    project_id: int | None = Query(None, description="Optional project ID to filter experiments"),
    status_in: list[C.ExperimentStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ExperimentStatus, query_param="status_in")),
    workflow_in: list[C.ExperimentWorkFlow] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ExperimentWorkFlow, query_param="workflow_in")),
    name: str | None = Query(None, description="Optional name to search experiments"),
    operator: str | None = Query(None, description="Optional operator name to search experiments"),
    id_search: str | None = Query(None, alias="id", description="Search by experiment ID"),
    library_types_in: list[C.LibraryType] | None = Depends(dependencies.parse_enum_ids(enum_type=C.LibraryType, query_param="library_types_in")),
    browse: str | None = Query(None, description="Optional browse context for experiment selection component"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Experiment, default=models.Experiment.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_user)
):
    table = ExperimentTable(route="render_experiment_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    if workflow_in:
        table.filter_values["workflow"] = workflow_in
    if library_types_in:
        table.filter_values["library_types"] = library_types_in

    stmt = Q.experiment.select(
        project_id=project_id,
        status_in=status_in,
        workflow_in=workflow_in,
        library_types_in=library_types_in,
    )
    if name:
        table.active_search_var = "name"
        table.active_query_value = name
        stmt = Q.experiment.search(name=name, statement=stmt)
    elif operator:
        table.active_search_var = "operator"
        table.active_query_value = operator
        stmt = Q.experiment.search(operator_name=operator, statement=stmt)
    elif id_search:
        table.active_search_var = "id"
        table.active_query_value = id_search
        if digits := "".join(filter(str.isdigit, id_search)):
            stmt = Q.experiment.select(id=int(digits), statement=stmt)

    if project_id is not None:
        if session.get_access_level(Q.project.permissions(project_id, current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException(f"User does not have permission to view experiments for project ID {project_id}.")
        table.template = "components/tables/project-experiment.html"
        table.url_params["project_id"] = project_id
    else:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("User does not have permission to view experiments.")
        table.template = "components/tables/experiment.html"
    
    if browse is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("User does not have permission to browse experiments.")
        table.template = "components/tables/browse-experiment.html"
        table.context["browse_context"] = browse
        table.url_params["browse"] = browse

    experiments = table.paginate(
        session, stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Experiment.operator),
            orm.selectinload(models.Experiment.pools),
            orm.selectinload(models.Experiment.sequencer),
            orm.with_expression(
                models.Experiment._library_types,
                models.Experiment.library_types.expression  # type: ignore
            ),
        ]
    )
    return table.make_response(experiments=experiments)


@router.get("/search")
def search_experiments(
    word: str | None = Query(None, description="Search word for experiment name"),
    selected_id: int | None = Query(None, description="Currently selected experiment"),
    _=Depends(dependencies.require_insider),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    stmt = Q.experiment.select()

    if selected_id is not None and not word:
        stmt = Q.experiment.select(id=selected_id, statement=stmt)
    elif word:
        stmt = Q.experiment.search(name=word, statement=stmt)
    else:
        stmt = stmt.order_by(models.Experiment.name.asc())

    return query_options.search_response(session, stmt, page=page, option=query_options.experiment_option)

@router.delete("/{experiment_id}/delete")
def delete_experiment(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider)
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    if not experiment.is_deleteable() and not current_user.is_admin:
        raise exc.NoPermissionsException()

    session.delete(experiment)
    return responses.htmx_response(
        redirect=responses.url_for("experiments_page"),
        flash=responses.flash(f"Experiment '{experiment.name}' deleted.", "success")
    )

@router.get("/{experiment_id}/checklist")
def experiment_checklist(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider)
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id).options(
        orm.selectinload(models.Experiment.checklist_logs).selectinload(models.ChecklistLog.actor),
    ))
    checklist = experiment.get_checklist()
    can_be_edited = (experiment.status < C.ExperimentStatus.SEQUENCING) or current_user.is_admin
    
    return responses.htmx_response(
        template="components/checklists/experiment.html",
        experiment=experiment,
        can_be_edited=can_be_edited,
        checklist_history=checklists.history(experiment),
        **checklist,
    )


@router.post("/{experiment_id}/checklist-check/{step}")
def check_experiment_checklist_step(
    experiment_id: int,
    step: str,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    if step not in models.Experiment.MANUAL_CHECKLIST_STEPS:
        raise exc.BadRequestException(f"Unknown checklist step '{step}'.")

    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    if not experiment.pools:
        raise exc.BadRequestException("Add pools to the experiment first.")

    checklists.set_step(session, experiment, step, checked=True, actor_id=current_user.id)
    return responses.htmx_response(
        redirect=request.url_for("experiment_page", experiment_id=experiment.id).include_query_params(tab="checklist-tab"),
    )


@router.post("/{experiment_id}/checklist-uncheck/{step}")
def uncheck_experiment_checklist_step(
    experiment_id: int,
    step: str,
    request: Request,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider),
):
    if step not in models.Experiment.MANUAL_CHECKLIST_STEPS:
        raise exc.BadRequestException(f"Unknown checklist step '{step}'.")

    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    checklists.set_step(session, experiment, step, checked=False, actor_id=current_user.id)
    return responses.htmx_response(
        redirect=request.url_for("experiment_page", experiment_id=experiment.id).include_query_params(tab="checklist-tab"),
    )

@router.get("/{experiment_id}/overview", dependencies=[Depends(dependencies.require_insider)])
def experiment_overview(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict:
    """Requests → libraries → pools → lanes of the experiment (JSON for static/js/overview-graph.js)."""
    if not session.exists(Q.experiment.select(id=experiment_id)):
        raise exc.NotFoundException(f"Experiment with ID {experiment_id} not found.")
    return overview.experiment_graph(session, experiment_id)


_STATS_BASE_COLS = {"library_id", "library_name", "pool_id", "pool_name", "num_reads", "lane"}


def _opt(value):
    return None if value is None or pd.isna(value) else value


def _qc_value(value):
    if isinstance(value, (list, dict)):
        return str(value)
    if _opt(value) is None:
        return ""
    if isinstance(value, float):
        return round(value, 3)
    return value


def _library_rows(raw: pd.DataFrame, total_reads: int) -> tuple[list[dict], dict | None, list[str]]:
    """Per-library rows (reads, per-lane split, QC) of an experiment; the undetermined row (no library) separately."""
    rows: dict[int | None, dict] = {}
    for rec in raw.itertuples(index=False):
        key = int(rec.library_id) if _opt(rec.library_id) is not None else None
        row = rows.setdefault(key, {
            "id": key,
            "name": rec.library_name if key is not None else "Undetermined",
            "pool_id": int(rec.pool_id) if _opt(rec.pool_id) is not None else None,
            "pool_name": _opt(rec.pool_name),
            "num_reads": 0, "lanes": {}, "qc": {},
        })
        reads = int(_opt(rec.num_reads) or 0)
        row["num_reads"] += reads
        row["lanes"][int(rec.lane)] = row["lanes"].get(int(rec.lane), 0) + reads

    # QC metrics are free-form keys, averaged over lanes weighted by reads
    qc_df = T.experiment_stats(raw.copy(), per_lane=False, expand_qc_=True, weighted_average=True)
    qc_keys = [
        col for col in qc_df.columns
        if isinstance(col, str) and col not in _STATS_BASE_COLS and qc_df[col].notna().any()
    ]
    for rec in qc_df.to_dict("records"):
        key = int(rec["library_id"]) if _opt(rec["library_id"]) is not None else None
        if key in rows:
            rows[key]["qc"] = {k: _qc_value(rec.get(k)) for k in qc_keys}

    max_reads = max((row["num_reads"] for row in rows.values()), default=0) or 1
    for row in rows.values():
        row["pct_of_run"] = row["num_reads"] / total_reads * 100 if total_reads else 0.0
        row["bar_pct"] = row["num_reads"] / max_reads * 100
        row["lanes"] = [
            {"lane": lane, "num_reads": reads, "width": reads / max_reads * 100,
             "pct": reads / row["num_reads"] * 100 if row["num_reads"] else 0.0}
            for lane, reads in sorted(row["lanes"].items()) if reads > 0
        ]

    undetermined = rows.pop(None, None)
    libraries = sorted(rows.values(), key=lambda r: r["num_reads"], reverse=True)
    return libraries, undetermined, qc_keys


def _pool_rows(
    session: SyncSession, experiment_id: int, libraries: list[dict], total_reads: int,
    cfg: config.ExperimentStatsConfig,
) -> tuple[list[dict], dict | None]:
    """Per-pool rows (sequenced vs planned/requested reads, flag, its libraries); the undetermined row separately."""
    stats = T.pool_num_reads_stats(
        session.get_pandas(Q.pd.pool_num_reads_stats_sequenced(experiment_id), limit=None),
        session.get_pandas(Q.pd.pool_num_reads_stats_planned(experiment_id), limit=None),
    )
    rows = []
    undetermined = None
    for rec in stats.to_dict("records"):
        pool_id = _opt(rec["pool_id"])
        seq_vs_planned = _opt(rec["sequenced_vs_planned"])
        flag = None
        if seq_vs_planned is not None:
            if seq_vs_planned < cfg.under_planned_pct:
                flag = "under"
            elif seq_vs_planned > cfg.over_planned_pct:
                flag = "over"
        row = {
            "id": int(pool_id) if pool_id is not None else None,
            "name": rec["pool_name"] if pool_id is not None else "Undetermined",
            "num_reads": int(_opt(rec["num_reads"]) or 0),
            "planned": _opt(rec["num_planned_reads"]),
            "requested": _opt(rec["num_reads_requested"]),
            "seq_vs_planned": float(seq_vs_planned) if seq_vs_planned is not None else None,
            "flag": flag,
            "libraries": [],
        }
        if row["id"] is None:
            undetermined = row
        else:
            rows.append(row)

    # pool bars show the share of the whole flow cell, the bars of a pool's libraries their share of that pool
    by_id = {row["id"]: row for row in rows}
    for library in libraries:
        if (pool := by_id.get(library["pool_id"])) is not None:
            pct_of_pool = library["num_reads"] / pool["num_reads"] * 100 if pool["num_reads"] else 0.0
            pool["libraries"].append({**library, "bar_pct": pct_of_pool, "pct_of_pool": pct_of_pool})
    for row in rows + ([undetermined] if undetermined else []):
        row["pct_of_run"] = row["num_reads"] / total_reads * 100 if total_reads else 0.0
        row["bar_pct"] = row["pct_of_run"]

    rows.sort(key=lambda r: r["num_reads"], reverse=True)
    return rows, undetermined


@router.get("/{experiment_id}/stats", dependencies=[Depends(dependencies.require_insider)])
def experiment_stats(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    raw = session.get_pandas(Q.pd.experiment_stats(experiment.id), limit=None)
    if raw.empty:
        return responses.htmx_response(template="components/experiment-stats.html", experiment=experiment, has_stats=False)

    cfg = config.settings.app_config.experiment_stats
    total_reads = int(raw["num_reads"].sum())
    libraries, undetermined_library, qc_keys = _library_rows(raw, total_reads)
    pools, undetermined_pool = _pool_rows(session, experiment.id, libraries, total_reads, cfg)

    undetermined_pct = undetermined_library["pct_of_run"] if undetermined_library else 0.0
    return responses.htmx_response(
        template="components/experiment-stats.html",
        experiment=experiment, has_stats=True,
        libraries=libraries, undetermined_library=undetermined_library, qc_keys=qc_keys,
        pools=pools, undetermined_pool=undetermined_pool,
        lanes=sorted({int(lane) for lane in raw["lane"].unique()}),
        num_total_reads=total_reads,
        num_library_reads=total_reads - (undetermined_library["num_reads"] if undetermined_library else 0),
        undetermined_pct=undetermined_pct,
        undetermined_warn=undetermined_pct > cfg.undetermined_warn_pct,
        stats_config=cfg,
    )

@router.delete("/{experiment_id}/remove-pool/{pool_id}", dependencies=[Depends(dependencies.require_insider)])
def remove_pool_from_experiment(
    experiment_id: int,
    pool_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    pool = session.get_one(Q.pool.select(id=pool_id))

    if pool not in experiment.pools:
        raise exc.BadRequestException(f"Pool {pool.name} is not associated with Experiment {experiment.name}.")

    # also drops the pool's lane links and its libraries' experiment_id
    actions.unlink_pool_experiment(session, experiment_id=experiment.id, pool_id=pool.id)

    return responses.htmx_response(
        # redirect=responses.url_for("experiment_page", experiment_id=experiment.id),
        flash=responses.flash(f"Pool '{pool.name}' removed from Experiment '{experiment.name}'.", "success")
    )


@router.post("/{experiment_id}/lane-pool/{lane}/{pool_id}", dependencies=[Depends(dependencies.require_insider)])
def add_pool_to_lane(
    experiment_id: int,
    lane_num: int = Path(..., alias="lane"),
    pool_id: int = Path(...),
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    if experiment.workflow.combined_lanes:
        raise exc.BadRequestException(f"Experiment {experiment.name} is a combined-lane workflow, and does not support lane-specific pools.")
    
    from loguru import logger
    logger.debug(f"Adding Pool {pool_id} to Lane {lane_num} in Experiment {experiment_id}")
    pool = session.get_one(Q.pool.select(id=pool_id, experiment_id=experiment.id))
    lane = session.get_one(Q.lane.select(experiment_id=experiment.id, number=lane_num))
    
    actions.add_pool_to_lane(session, experiment=experiment, pool=pool, lane=lane)

    return responses.htmx_response(
        redirect=responses.url_for("experiment_page", experiment_id=experiment.id),
        flash=responses.flash(f"Pool '{pool.name}' added to Experiment '{experiment.name}' on Lane {lane.number}.", "success")
    )

@router.delete("/{experiment_id}/lane-pool/{lane}/{pool_id}", dependencies=[Depends(dependencies.require_insider)])
def remove_pool_from_lane(
    experiment_id: int,
    lane_num: int = Path(..., alias="lane"),
    pool_id: int = Path(...),
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    if experiment.workflow.combined_lanes:
        raise exc.BadRequestException(f"Experiment {experiment.name} is a combined-lane workflow, and does not support lane-specific pools.")
    
    pool = session.get_one(Q.pool.select(id=pool_id))

    if pool not in experiment.pools:
        raise exc.BadRequestException(f"Pool {pool.name} is not associated with Experiment {experiment.name}.")
    
    lane = session.get_one(Q.lane.select(experiment_id=experiment.id, number=lane_num))
    
    actions.remove_pool_from_lane(session, experiment=experiment, pool=pool, lane=lane)

    return responses.htmx_response(
        redirect=responses.url_for("experiment_page", experiment_id=experiment.id),
        flash=responses.flash(f"Pool '{pool.name}' removed from Experiment '{experiment.name}' on Lane {lane.number}.", "success")
    )

@router.get("/{experiment_id}/sample-pooling-table/{file_id}", dependencies=[Depends(dependencies.require_insider)])
def render_experiment_sample_pooling_table(
    experiment_id: int,
    file_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    file = session.get_one(Q.media_file.select(id=file_id, experiment_id=experiment.id))

    if not os.path.exists(filepath := os.path.join(config.settings.app_config.media_folder, file.path)):
        raise exc.NotFoundException()

    df = pd.read_csv(filepath, sep="\t")

    if "lane" not in df.columns:
        target_molarity = df["target_molarity"].values[0]
        target_total_volume = df["target_total_volume"].values[0]
        pipet = df["pipet"].sum()
        eb_volume = target_total_volume - pipet
        return responses.htmx_response(
            template="components/experiment-pooling-ratios.html", experiment=experiment, df=df,
            target_molarity=target_molarity, target_total_volume=target_total_volume,
            pipet=pipet, eb_volume=eb_volume
        )
    
    return responses.htmx_response(template="components/lane-pooling-ratios.html", experiment=experiment, df=df)


@router.get("/render-feed", dependencies=[Depends(dependencies.require_insider)])
def render_experiment_feed(
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    session: SyncSession = Depends(dependencies.db_session),
):
    PAGE_LIMIT = 10
    experiments, total = session.page(
        Q.experiment.select(
            status_in=[
                C.ExperimentStatus.DRAFT,
                C.ExperimentStatus.LOADED,
                C.ExperimentStatus.SEQUENCING,
                C.ExperimentStatus.SEQUENCED,
            ]
        ),
        page=page,
        limit=PAGE_LIMIT,
        order_by=models.Experiment.name.desc(),
        options=[orm.selectinload(models.Experiment.operator)],
    )
    return responses.htmx_response(
        template="components/dashboard/experiments-feed.html",
        experiments=experiments,
        current_page=page,
        limit=PAGE_LIMIT,
        total=total,
    )


router.include_router(forms.models.ExperimentForm.Router())
router.include_router(forms.actions.dist_reads.DistributeReadsSeparateAction.Router())
router.include_router(forms.actions.dist_reads.DistributeReadsCombinedAction.Router())
router.include_router(forms.actions.SelectExperimentPoolsAction.Router())
router.include_router(forms.actions.DilutePoolsAction.Router())
router.include_router(forms.actions.lane_pools.LanePoolsSeparateAction.Router())
router.include_router(forms.actions.lane_pools.LanePoolsCombinedAction.Router())
router.include_router(forms.actions.load_flowcell.LoadFlowCellSeparateAction.Router())
router.include_router(forms.actions.load_flowcell.LoadFlowCellCombinedAction.Router())
router.include_router(forms.actions.SetExperimentCyclesAction.Router())
router.include_router(forms.actions.GenerateSequencerLoadingChecklistAction.Router())
router.include_router(data_browser_router(DataScope(
    entity="experiment", label="experiment", permissions=experiment_data_permissions,
    page_route="experiment_page", tab="experiment-data_paths-tab",
)))
