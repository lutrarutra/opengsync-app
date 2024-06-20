import json
from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, render_template, flash, url_for
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse, LibraryStatus, LibraryType

from .... import db, logger  # noqa
from ....forms.workflows import library_pooling as forms
from ....forms import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_pooling_workflow = Blueprint("library_pooling_workflow", __name__, url_prefix="/api/workflows/library_pooling/")


@library_pooling_workflow.route("<int:pool_id>/begin", methods=["GET"])
@login_required
def begin(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    context["pool"] = pool
    
    form = SelectSamplesForm(
        workflow="library_pooling", context=context,
        select_samples=False, select_pools=False,
        library_status_filter=[LibraryStatus.PREPARING, LibraryStatus.STORED]
    )
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

    form = SelectSamplesForm(workflow="library_pooling", formdata=request.form, context=context)
    if not form.validate():
        return form.make_response()

    _, library_table, _ = form.get_tables()

    for _, row in library_table.iterrows():
        if (library := db.get_library(row["id"])) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        if library.pool_id is not None:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        library.pool_id = pool.id
        library.status_id = LibraryStatus.POOLED.id
        library = db.update_library(library)

    flash("Changes saved to pool", "success")
    return make_response(redirect=url_for("pools_page.pool_page", pool_id=pool.id))
