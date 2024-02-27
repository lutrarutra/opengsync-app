from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.core.categories import HttpResponse, SeqRequestStatus
from ... import forms, db, tools

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

experiments_page_bp = Blueprint("experiments_page", __name__)


@experiments_page_bp.route("/experiments")
@login_required
def experiments_page():
    if not current_user.is_insider():
        return abort(HttpResponse.BAD_REQUEST.id)
    
    experiments, n_pages = db.get_experiments()

    experiment_form = forms.ExperimentForm(user=current_user)

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
        return abort(HttpResponse.FORBIDDEN.id)
    
    with DBSession(db) as session:
        if (experiment := session.get_experiment(experiment_id)) is None:
            return abort(HttpResponse.NOT_FOUND.id)
        
        if not current_user.is_insider():
            return abort(HttpResponse.FORBIDDEN.id)

        pools = session.get_available_pools_for_experiment(experiment_id)

        seq_requests, seq_requests_n_pages = session.get_seq_requests(
            sort_by="id", descending=True, experiment_id=experiment_id
        )

        available_seq_requests_sort = "submitted_time"

        available_seq_requests, available_seq_requests_n_pages = session.get_seq_requests(
            exclude_experiment_id=experiment_id,
            with_statuses=[SeqRequestStatus.PREPARATION],
            sort_by=available_seq_requests_sort, descending=True,
        )
        experiment_lanes = session.get_lanes_in_experiment(experiment_id)

        libraries, libraries_n_pages = session.get_libraries(
            sort_by="id", descending=True, experiment_id=experiment_id
        )

        experiment_form = forms.ExperimentForm(experiment=experiment)
        pooling_input_form = forms.pooling.PoolingInputForm()
        comment_form = forms.ExperimentCommentForm(experiment_id=experiment_id)

        path_list = [
            ("Experiments", url_for("experiments_page.experiments_page")),
            (f"Experiment {experiment_id}", ""),
        ]

        libraries_df = db.get_experiment_libraries_df(experiment_id)
        libraries_df = tools.check_indices(libraries_df)

        return render_template(
            "experiment_page.html",
            experiment=experiment,
            experiment_form=experiment_form,
            experiment_lanes=experiment_lanes,
            path_list=path_list,
            pools=pools,
            pools_n_pages=0,
            seq_requests=seq_requests,
            libraries_df=libraries_df,
            seq_requests_n_pages=seq_requests_n_pages,
            libraries=libraries,
            libraries_n_pages=libraries_n_pages,
            libraries_active_page=0,
            comment_form=comment_form,
            file_input_form=forms.ExperimentAttachmentForm(experiment_id=experiment_id),
            pooling_input_form=pooling_input_form,
            available_seq_requests_n_pages=available_seq_requests_n_pages,
            available_seq_requests_active_page=0,
            available_seq_requests=available_seq_requests,
            complete_experiment_form=forms.CompleteExperimentForm(),
            available_seq_requests_current_sort=available_seq_requests_sort,
            available_seq_requests_current_sort_order="desc",
            selected_sequencer=experiment.sequencer.name,
            selected_user=experiment.sequencing_person,
        )
