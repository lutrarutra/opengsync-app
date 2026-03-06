from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models

from ... import db, logic
from ...core import wrappers

lanes_htmx = Blueprint("lanes_htmx", __name__, url_prefix="/htmx/lanes/")


@wrappers.htmx_route(lanes_htmx, db=db)
def browse(current_user: models.User, workflow: str):
    return make_response(render_template(**logic.lane.get_browse_context(current_user=current_user, request=request, workflow=workflow)))
    