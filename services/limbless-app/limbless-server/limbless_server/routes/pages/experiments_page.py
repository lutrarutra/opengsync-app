from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse, PoolStatus, FileType

from ... import forms, db, tools, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

experiments_page_bp = Blueprint("experiments_page", __name__)


@experiments_page_bp.route("/experiments")
@login_required
def experiments_page():
    if not current_user.is_insider():
        return abort(HTTPResponse.BAD_REQUEST.id)

    return render_template("experiments_page.html")


@experiments_page_bp.route("/experiments/<int:experiment_id>")
@login_required
def experiment_page(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)

        pools, _ = db.get_pools(experiment_id=experiment_id, sort_by="id", descending=True, limit=None)

        comment_form = forms.comment.ExperimentCommentForm(experiment_id=experiment_id)
        file_input_form = forms.file.ExperimentAttachmentForm(experiment_id=experiment_id)

        experiment_lanes: dict[int, list[int]] = {}
        _lane_capacities: dict[int, float] = {}

        qubit_concentration_measured = len(pools) > 0
        avg_framgnet_size_measured = len(pools) > 0
        all_lanes_qced = len(experiment.lanes) > 0
        flow_cell_ready = len(experiment.lanes) > 0
        
        for lane in experiment.lanes:
            all_lanes_qced = all_lanes_qced and lane.is_qced()
            flow_cell_ready = flow_cell_ready and lane.is_loaded()
            experiment_lanes[lane.number] = []
            _lane_capacities[lane.number] = 0
            
            for pool in lane.pools:
                experiment_lanes[lane.number].append(pool.id)
                if pool.num_m_reads_requested is not None:
                    _lane_capacities[lane.number] += pool.num_m_reads_requested

        lane_capacities: dict[int, tuple[float, float]] = dict([(lane.number, (_lane_capacities[lane.number], 100.0 * _lane_capacities[lane.number] / experiment.flowcell_type.max_m_reads_per_lane)) for lane in experiment.lanes])
        all_pools_laned = len(pools) > 0
        all_pools_qced = len(pools) > 0

        for pool in pools:
            laned = False
            for pool_ids in experiment_lanes.values():
                if pool.id in pool_ids:
                    laned = True
                    break
            all_pools_laned = all_pools_laned and laned

            all_pools_qced = all_pools_qced and pool.is_qced()
            if not all_pools_laned or not all_pools_qced:
                break
            
        can_be_loaded = all_pools_laned and all_pools_qced

        path_list = [
            ("Experiments", url_for("experiments_page.experiments_page")),
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
            file_input_form=file_input_form,
            comment_form=comment_form,
            experiment_lanes=experiment_lanes,
            selected_sequencer=experiment.sequencer.name,
            selected_user=experiment.operator,
            all_pools_laned=all_pools_laned,
            all_pools_qced=all_pools_qced,
            can_be_loaded=can_be_loaded,
            all_lanes_qced=all_lanes_qced,
            flow_cell_ready=flow_cell_ready,
            laning_completed=laning_completed,
            lane_capacities=lane_capacities,
            Pool=models.Pool
        )
