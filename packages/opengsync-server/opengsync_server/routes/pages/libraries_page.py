from flask import Blueprint, render_template, url_for, request

from opengsync_db import models, queries as Q
from opengsync_db.categories import AccessLevel

from ... import db, forms
from ...core import wrappers, exceptions
libraries_page_bp = Blueprint("libraries_page", __name__)


@wrappers.page_route(libraries_page_bp, db=db, cache_timeout_seconds=360)
def libraries():
    return render_template("libraries_page.html", title="Libraries")


@wrappers.page_route(libraries_page_bp, "libraries", db=db, cache_timeout_seconds=360)
def library(current_user: models.User, library_id: int):
    if (library := db.session.first(Q.library.select(id=library_id))) is None:
        raise exceptions.NotFoundException()
    
    access_level = db.session.get_access_level(Q.library.permissions(library.id, current_user.id))
    if access_level < AccessLevel.READ:
        raise exceptions.NoPermissionsException()

    path_list = [
        ("Libraries", url_for("libraries_page.libraries")),
        (f"Library {library.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_request_pages")),
                (f"Request {id}", url_for("seq_request_page", seq_request_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments")),
                (f"Experiment {id}", url_for("experiments_page.experiment", experiment_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "sample":
            path_list = [
                ("Samples", url_for("sample_pages")),
                (f"Sample {id}", url_for("sample_page", sample_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "pool":
            path_list = [
                ("Pools", url_for("pools_page.pools")),
                (f"Pool {id}", url_for("pools_page.pool", pool_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "lab_prep":
            path_list = [
                ("Lab Preps", url_for("lab_preps_page.lab_preps")),
                (f"Lab Prep {id}", url_for("lab_preps_page.lab_prep", lab_prep_id=id)),
                (f"Library {library.id}", ""),
            ]

    library_form = forms.models.LibraryForm(library=library)

    return render_template(
        "library_page.html",
        library=library,
        path_list=path_list,
        library_form=library_form,
        title=f"Library {f'#{library.id:04d}'}"
    )
