from flask import Blueprint, render_template, url_for, request

from opengsync_db import models
from opengsync_db.categories import LibraryStatus

from ... import db
from ...core import wrappers, exceptions
lab_preps_page_bp = Blueprint("lab_preps_page", __name__)


@wrappers.page_route(lab_preps_page_bp, db=db, cache_timeout_seconds=360)
def lab_preps(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    return render_template("lab_preps_page.html")


@wrappers.page_route(lab_preps_page_bp, db=db, cache_timeout_seconds=360)
def lab_prep(current_user: models.User, lab_prep_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()
    
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