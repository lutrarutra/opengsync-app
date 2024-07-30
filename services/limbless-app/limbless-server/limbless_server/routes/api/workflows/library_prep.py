from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response, current_app, url_for, flash
from flask_login import login_required
from flask_htmx import make_response

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse

from .... import db, logger, forms  # noqa
from ....forms.SelectSamplesForm import SelectSamplesForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_prep_workflow = Blueprint("library_prep_workflow", __name__, url_prefix="/api/workflows/library_prep/")


@library_prep_workflow.route("begin/<int:lab_prep_id>", methods=["GET"])
@db_session(db)
@login_required
def begin(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    # if pool.type == PoolType.RNA_SEQ:
    #     form = forms.RNAPrepForm(pool=pool, formdata=request.form)
    # else:
    #     return abort(HTTPResponse.BAD_REQUEST.id)

    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = SelectSamplesForm.create_workflow_form("library_prep", context={"lab_prep": lab_prep})
    return form.make_response()


@library_prep_workflow.route("select/<int:lab_prep_id>", methods=["POST"])
@db_session(db)
@login_required
def select(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = SelectSamplesForm.create_workflow_form("library_prep", formdata=request.form, context={"lab_prep": lab_prep})
    
    if not form.validate():
        return form.make_response()
    
    _, library_table, _, _ = form.get_tables()

    for _, row in library_table.iterrows():
        lab_prep = db.add_library_to_prep(
            lab_prep_id=lab_prep_id,
            library_id=row["id"],
        )

    flash("Libraries added!", "success")
    return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=lab_prep_id))