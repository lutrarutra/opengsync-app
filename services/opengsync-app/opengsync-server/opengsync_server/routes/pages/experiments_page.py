from flask import Blueprint, render_template, url_for, request

from opengsync_db import models
from opengsync_db.categories import MediaFileType

from ... import db
from ...core import wrappers, exceptions
experiments_page_bp = Blueprint("experiments_page", __name__)


@wrappers.page_route(experiments_page_bp, db=db, cache_timeout_seconds=360)
def experiments(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return render_template("experiments_page.html")


@wrappers.page_route(experiments_page_bp, "experiments", db=db, cache_timeout_seconds=360)
def experiment(current_user: models.User, experiment_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    if (experiment := db.experiments.get(experiment_id)) is None:
        raise exceptions.NotFoundException()

    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    pools, _ = db.pools.find(experiment_id=experiment_id, sort_by="id", descending=True, limit=None)

    experiment_lanes: dict[int, list[int]] = {}

    all_lanes_qced = len(experiment.lanes) > 0
    flow_cell_ready = len(experiment.lanes) > 0

    for lane in experiment.lanes:
        all_lanes_qced = all_lanes_qced and lane.is_qced()
        flow_cell_ready = flow_cell_ready and lane.is_loaded()
        experiment_lanes[lane.number] = []

        for link in lane.pool_links:
            experiment_lanes[lane.number].append(link.pool_id)

    all_pools_laned = len(pools) > 0

    qubit_concentration_measured = len(pools) > 0
    avg_framgnet_size_measured = len(pools) > 0
    for pool in pools:
        laned = False
        for pool_ids in experiment_lanes.values():
            if pool.id in pool_ids:
                laned = True
                break
        all_pools_laned = all_pools_laned and laned
        qubit_concentration_measured = qubit_concentration_measured and pool.qubit_concentration is not None
        avg_framgnet_size_measured = avg_framgnet_size_measured and pool.avg_fragment_size is not None

        if not all_pools_laned and not qubit_concentration_measured and not avg_framgnet_size_measured:
            break
    
    can_be_loaded = all_pools_laned and qubit_concentration_measured and avg_framgnet_size_measured

    path_list = [
        ("Experiments", url_for("experiments_page.experiments")),
        (f"Experiment {experiment_id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "seq_run":
            path_list = [
                ("Runs", url_for("seq_runs_page.seq_runs")),
                (f"Run {id}", url_for("seq_runs_page.seq_run", seq_run_id=id)),
                (f"Experiment {experiment_id}", ""),
            ]
        elif page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Experiment {experiment_id}", ""),
            ]

    laning_completed = False
    for file in experiment.media_files:
        if file.type == MediaFileType.LANE_POOLING_TABLE:
            laning_completed = True
            break

    return render_template(
        "experiment_page.html",
        experiment=experiment,
        path_list=path_list,
        pools=pools,
        experiment_lanes=experiment_lanes,
        selected_sequencer=experiment.sequencer.name,
        selected_user=experiment.operator,
        all_pools_laned=all_pools_laned,
        qubit_concentration_measured=qubit_concentration_measured,
        avg_framgnet_size_measured=avg_framgnet_size_measured,
        can_be_loaded=can_be_loaded,
        all_lanes_qced=all_lanes_qced,
        flow_cell_ready=flow_cell_ready,
        laning_completed=laning_completed,
    )
