from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required, current_user

from limbless_db import db_session
from limbless_db.categories import HTTPResponse, LibraryStatus

from ... import db, logger, forms  # noqa

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
    
    can_be_completed = len(lab_prep.libraries) > 0
    for library in lab_prep.libraries:
        if library.status.id < LibraryStatus.POOLED.id:
            can_be_completed = False
            break
        
    path_list = [
        ("Preps", url_for("lab_preps_page.lab_preps_page")),
        (f"Prep {lab_prep.id}", ""),
    ]
    if (_from := request.args.get("from")) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries_page")),
                (f"Library {id}", url_for("libraries_page.library_page", library_id=id)),
                (f"Prep {lab_prep.id}", ""),
            ]

    return render_template(
        "lab_prep_page.html", lab_prep=lab_prep, can_be_completed=can_be_completed, path_list=path_list,
    )