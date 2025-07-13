from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse, FileType

from ... import forms, db, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

experiments_page_bp = Blueprint("experiments_page", __name__)


@experiments_page_bp.route("/experiments")
@login_required
def experiments_page():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return render_template("experiments_page.html")


@experiments_page_bp.route("/experiments/<int:experiment_id>")
@db_session(db)
@login_required
def experiment_page(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    if (experiment := db.get_experiment(experiment_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    pools, _ = db.get_pools(experiment_id=experiment_id, sort_by="id", descending=True, limit=None)

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
        ("Experiments", url_for("experiments_page.experiments_page")),
        (f"Experiment {experiment_id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "seq_run":
            path_list = [
                ("Runs", url_for("seq_runs_page.seq_runs_page")),
                (f"Run {id}", url_for("seq_runs_page.seq_run_page", seq_run_id=id)),
                (f"Experiment {experiment_id}", ""),
            ]
        elif page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries_page")),
                (f"Library {id}", url_for("libraries_page.library_page", library_id=id)),
                (f"Experiment {experiment_id}", ""),
            ]

    laning_completed = False
    for file in experiment.files:
        if file.type == FileType.LANE_POOLING_TABLE:
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
