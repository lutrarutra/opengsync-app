from flask import Blueprint, render_template, url_for, request

from opengsync_db import models

from ... import db
from ...core import wrappers, exceptions
seq_runs_page_bp = Blueprint("seq_runs_page", __name__)


@wrappers.page_route(seq_runs_page_bp, db=db, cache_timeout_seconds=60)
def seq_runs(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return render_template("seq_runs_page.html")


@wrappers.page_route(seq_runs_page_bp, "seq_runs", db=db, cache_timeout_seconds=60)
def seq_run(current_user: models.User, seq_run_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (seq_run := db.seq_runs.get(seq_run_id)) is None:
        raise exceptions.NotFoundException()
    
    experiment = db.experiments.get(seq_run.experiment_name)
    path_list = [
        ("Runs", url_for("seq_runs_page.seq_runs")),
        (f"Run {seq_run.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments")),
                (f"Experiment {id}", url_for("experiments_page.experiment", experiment_id=id)),
                (f"Run {seq_run.id}", ""),
            ]

    return render_template("seq_run_page.html", seq_run=seq_run, experiment=experiment, path_list=path_list)