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
    
    with DBSession(db) as session:
        experiments, n_pages = session.get_experiments()

        experiment_form = forms.models.ExperimentForm(user=current_user)

        return render_template(
            "experiments_page.html", experiment_form=experiment_form,
            experiments=experiments,
            experiments_n_pages=n_pages, experiments_active_page=0,
            experiments_current_sort="id", experiments_current_sort_order="desc"
        )


@experiments_page_bp.route("/experiments/<experiment_id>")
@login_required
def experiment_page(experiment_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        if not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)

        available_seq_requests_sort = "submitted_time"

        pools, _ = db.get_pools(experiment_id=experiment_id, sort_by="id", descending=True, limit=None)

        experiment_form = forms.models.ExperimentForm(experiment=experiment)
        pooling_input_form = forms.workflows.library_pooling.PoolingInputForm()
        comment_form = forms.comment.ExperimentCommentForm(experiment_id=experiment_id)
        file_input_form = forms.file.ExperimentAttachmentForm(experiment_id=experiment_id)

        experiment_lanes = {}
        lane_capacities = {}

        all_lanes_qced = True
        all_lanes_ready = True
        for lane in experiment.lanes:
            all_lanes_qced = all_lanes_qced and lane.is_qced()
            all_lanes_ready = all_lanes_ready and lane.is_ready()
            experiment_lanes[lane.number] = []
            lane_capacities[lane.number] = 0
            
            for pool in lane.pools:
                experiment_lanes[lane.number].append(pool.id)
                lane_capacities[lane.number] += pool.num_m_reads_requested

            lane_capacities[lane.number] = (lane_capacities[lane.number], 100.0 * lane_capacities[lane.number] / experiment.flowcell_type.max_m_reads_per_lane)

        all_pools_laned = True
        all_pools_qced = True
        for pool in pools:
            all_pools_laned = all_pools_laned and pool.status == PoolStatus.LANED
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
        experiment.comments

    return render_template(
        "experiment_page.html",
        experiment=experiment,
        experiment_form=experiment_form,
        path_list=path_list,
        pools=pools,
        libraries_active_page=0,
        file_input_form=file_input_form,
        comment_form=comment_form,
        pooling_input_form=pooling_input_form,
        available_seq_requests_active_page=0,
        experiment_lanes=experiment_lanes,
        available_seq_requests_current_sort=available_seq_requests_sort,
        available_seq_requests_current_sort_order="desc",
        selected_sequencer=experiment.sequencer.name,
        selected_user=experiment.operator,
        all_pools_laned=all_pools_laned,
        all_pools_qced=all_pools_qced,
        can_be_loaded=can_be_loaded,
        all_lanes_qced=all_lanes_qced,
        all_lanes_ready=all_lanes_ready,
        laning_completed=laning_completed,
        lane_capacities=lane_capacities,
        Pool=models.Pool
    )
