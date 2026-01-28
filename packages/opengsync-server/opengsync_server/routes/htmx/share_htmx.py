from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models

from ... import db, logic
from ...core import wrappers

share_htmx = Blueprint("share_htmx", __name__, url_prefix="/htmx/share_tokens/")


@wrappers.htmx_route(share_htmx, db=db, cache_timeout_seconds=120, cache_type="insider")
def get_share_tokens(current_user: models.User):
    context = logic.share_token.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(share_htmx, db=db, cache_timeout_seconds=120, cache_type="insider")
def get_data_paths(current_user: models.User):    
    context = logic.data_path.get_table_context(current_user=current_user, request=request)
    return make_response(render_template(**context))