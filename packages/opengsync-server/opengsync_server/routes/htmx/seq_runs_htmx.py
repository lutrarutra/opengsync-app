from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models

from ... import db, logic
from ...core import wrappers, exceptions

seq_runs_htmx = Blueprint("seq_runs_htmx", __name__, url_prefix="/htmx/seq_run/")


@wrappers.htmx_route(seq_runs_htmx, db=db, cache_timeout_seconds=60, cache_type="insider")
def get(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    context = logic.seq_run.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))
