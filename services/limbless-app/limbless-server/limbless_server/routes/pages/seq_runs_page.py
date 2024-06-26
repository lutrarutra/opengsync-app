from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request
from flask_login import login_required

from limbless_db import models, DBSession
from limbless_db.categories import HTTPResponse, FileType

from ... import forms, db, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

seq_runs_page_bp = Blueprint("seq_runs_page", __name__)


@seq_runs_page_bp.route("/seq_runs")
@login_required
def seq_runs_page():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return render_template("seq_runs_page.html")


@seq_runs_page_bp.route("/seq_runs/<int:seq_run_id>")
@login_required
def seq_run_page(seq_run_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (seq_run := db.get_seq_run(seq_run_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    experiment = db.get_experiment(name=seq_run.experiment_name)
    path_list = [
        ("Runs", url_for("seq_runs_page.seq_runs_page")),
        (f"Run {seq_run.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments_page")),
                (f"Experiment {id}", url_for("experiments_page.experiment_page", experiment_id=id)),
                (f"Run {seq_run.id}", ""),
            ]

    return render_template("seq_run_page.html", seq_run=seq_run, experiment=experiment, path_list=path_list)