from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import library_prep as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_prep_workflow = Blueprint("library_prep_workflow", __name__, url_prefix="/api/workflows/library_prep/")


@library_prep_workflow.route("<int:pool_id>/begin", methods=["GET"])
@db_session(db)
@login_required
def begin(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.RNAPrepForm(pool=pool, formdata=request.form)
    form.prepare()
    return form.make_response()


@library_prep_workflow.route("<int:pool_id>/save", methods=["POST"])
@db_session(db)
@login_required
def save(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.RNAPrepForm(pool=pool, formdata=request.form)
    return form.process_request(current_user, "save")


@library_prep_workflow.route("<int:pool_id>/update", methods=["POST"])
@db_session(db)
@login_required
def update(pool_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (pool := db.get_pool(pool_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.RNAPrepForm(pool=pool, formdata=request.form)
    return form.process_request(current_user, "update")
