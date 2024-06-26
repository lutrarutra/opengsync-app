from flask import Blueprint, request
from flask_htmx import make_response

from limbless_db.categories import HTTPResponse, ExperimentStatus, RunStatus
from ... import forms, db, logger

seq_run_api = Blueprint("seq_run_api", __name__, url_prefix="/api/seq_run/")


@seq_run_api.route("create", methods=["POST"])
def create():
    form = forms.models.SeqRunForm(request.form, csrf_enabled=False)
    validated = form.validate()

    if not validated:
        if "experiment_name" in form.errors.keys() and "experiment_name not unique" in form.errors["experiment_name"]:
            return make_response("SeqRun already exists", 201)
        
        return make_response(str(form.errors), HTTPResponse.BAD_REQUEST.id)
    
    seq_run = form.create_seq_run()
    
    return make_response("OK")


@seq_run_api.route("<string:experiment_name>/update_status/<int:status_id>", methods=["PUT"])
def update_status(experiment_name: str, status_id: int):
    if (seq_run := db.get_seq_run(experiment_name=experiment_name)) is None:
        return make_response("SeqRun not found", HTTPResponse.NOT_FOUND.id)
    
    try:
        status = ExperimentStatus.get(status_id)
    except ValueError:
        return make_response("Invalid status", HTTPResponse.BAD_REQUEST.id)
    
    seq_run.status_id = status.id
    seq_run = db.update_seq_run(seq_run)

    if (experiment := db.get_experiment(name=seq_run.experiment_name)) is not None:
        if seq_run.status == RunStatus.FINISHED:
            experiment.status_id = ExperimentStatus.FINISHED.id
            db.update_experiment(experiment)
        elif seq_run.status == RunStatus.FAILED:
            experiment.status_id = ExperimentStatus.FAILED.id
            db.update_experiment(experiment)
        elif seq_run.status == RunStatus.RUNNING:
            experiment.status_id = ExperimentStatus.SEQUENCING.id
            db.update_experiment(experiment)
        elif seq_run.status == RunStatus.ARCHIVED:
            experiment.status_id = ExperimentStatus.ARCHIVED.id
            db.update_experiment(experiment)
    
    return make_response("OK")
