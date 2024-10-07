from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from limbless_db import db_session
from limbless_db.categories import HTTPResponse

from ... import db, logger

lab_preps_page_bp = Blueprint("lab_preps_page", __name__)


@lab_preps_page_bp.route("/preps", methods=["GET"])
@login_required
def lab_preps_page():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    return render_template("lab_preps_page.html")


@lab_preps_page_bp.route("/preps/<int:lab_prep_id>", methods=["GET"])
@db_session(db)
@login_required
def lab_prep_page(lab_prep_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    can_be_completed = True
    for library in lab_prep.libraries:
        if library.pool_id is None:
            can_be_completed = False
            break

    return render_template("lab_prep_page.html", lab_prep=lab_prep, can_be_completed=can_be_completed)