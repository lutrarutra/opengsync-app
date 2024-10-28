from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, flash, url_for
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms import SelectSamplesForm
from ....forms.workflows import library_pooling as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_pooling_workflow = Blueprint("library_pooling_workflow", __name__, url_prefix="/api/workflows/library_pooling/")


@library_pooling_workflow.route("browse_pool", methods=["GET"])
@login_required
def browse_pool() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (seq_request_id := request.args.get("seq_request_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    try:
        seq_request_id = int(seq_request_id)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    context = {"seq_request": seq_request}
    form = forms.PoolSelectForm(context=context)
    return form.make_response()


@library_pooling_workflow.route("select_pool", methods=["POST"])
@login_required
def select_pool() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.PoolSelectForm(formdata=request.form)
    if not form.validate():
        return form.make_response()
    
    pool_id = form.pool.selected.data
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if (seq_request_id := request.args.get("seq_request_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    try:
        seq_request_id = int(seq_request_id)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = SelectSamplesForm.create_workflow_form("library_pooling", context={"seq_request": seq_request, "pool": pool})
    return form.make_response()


@library_pooling_workflow.route("<int:pool_id>/begin", methods=["GET"])
@login_required
def begin(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    context["pool"] = pool
    
    form = SelectSamplesForm.create_workflow_form("library_pooling", context=context)
    
    return form.make_response()


@library_pooling_workflow.route("select", methods=["POST"])
@db_session(db)
@login_required
def select() -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool_id := request.form.get("pool_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    try:
        pool_id = int(pool_id)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    context = {"pool": pool}

    form = SelectSamplesForm.create_workflow_form("library_pooling", formdata=request.form, context=context)

    if not form.validate():
        return form.make_response()

    _, library_table, _, _ = form.get_tables()

    for _, row in library_table.iterrows():
        if (library := db.get_library(int(row["id"]))) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        db.pool_library(library_id=library.id, pool_id=pool.id)

    flash("Changes saved to pool", "success")
    return make_response(redirect=url_for("pools_page.pool_page", pool_id=pool.id))
