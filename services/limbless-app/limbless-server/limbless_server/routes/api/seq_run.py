from flask import Blueprint, request
from flask_htmx import make_response

from limbless_db.categories import HTTPResponse, SequencingStatus
from ... import forms, db

seq_run_api = Blueprint("seq_run", __name__, url_prefix="/api/seq_run/")


@seq_run_api.route("create", methods=["POST"])
def create():
    form = forms.SeqRunForm(request.form, csrf_enabled=False)
    validated = form.validate()
    if not validated:
        return make_response(
            str(form.errors), HTTPResponse.BAD_REQUEST.id,
        )
    
    form.create_seq_run()
    
    return make_response("OK")


@seq_run_api.route("<string:experiment_name>/complete", methods=["PUT"])
def complete(experiment_name: str):
    if (seq_run := db.get_seq_run(experiment_name=experiment_name)) is None:
        return make_response(
            "SeqRun not found", HTTPResponse.NOT_FOUND.id,
        )
    
    seq_run.status_id = SequencingStatus.DONE.id
    db.update_seq_run(seq_run)
    
    return make_response("OK")
