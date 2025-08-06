from flask import Blueprint, render_template, abort, url_for, request
from flask_login import current_user

from opengsync_db.categories import HTTPResponse, LibraryStatus

from ... import db, page_route  # noqa

lab_preps_page_bp = Blueprint("lab_preps_page", __name__)


@page_route(lab_preps_page_bp, db=db)
def lab_preps():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    return render_template("lab_preps_page.html")


@page_route(lab_preps_page_bp, db=db)
def lab_prep(lab_prep_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    can_be_completed = len(lab_prep.libraries) > 0
    contains_mux_libraries = False
    for library in lab_prep.libraries:
        if library.status.id < LibraryStatus.POOLED.id:
            can_be_completed = False
        
        if library.mux_type is not None:
            contains_mux_libraries = True
                
        if can_be_completed and contains_mux_libraries:
            break
        
    path_list = [
        ("Preps", url_for("lab_preps_page.lab_preps")),
        (f"Prep {lab_prep.id}", ""),
    ]
    if (_from := request.args.get("from")) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Prep {lab_prep.id}", ""),
            ]

    return render_template(
        "lab_prep_page.html", lab_prep=lab_prep, can_be_completed=can_be_completed, path_list=path_list,
        contains_mux_libraries=contains_mux_libraries
    )