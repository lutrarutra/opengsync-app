from typing import TYPE_CHECKING
from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from opengsync_db import db_session
from opengsync_db.models import User
from opengsync_db.categories import HTTPResponse
from ... import db, forms

if TYPE_CHECKING:
    current_user: User = None   # type: ignore
else:
    from flask_login import current_user

libraries_page_bp = Blueprint("libraries_page", __name__)


@libraries_page_bp.route("/libraries")
@login_required
def libraries_page():
    return render_template("libraries_page.html")


@libraries_page_bp.route("/libraries/<int:library_id>")
@db_session(db)
@login_required
def library_page(library_id):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    path_list = [
        ("Libraries", url_for("libraries_page.libraries_page")),
        (f"Library {library.id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests_page")),
                (f"Request {id}", url_for("seq_requests_page.seq_request_page", seq_request_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments_page")),
                (f"Experiment {id}", url_for("experiments_page.experiment_page", experiment_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "sample":
            path_list = [
                ("Samples", url_for("samples_page.samples_page")),
                (f"Sample {id}", url_for("samples_page.sample_page", sample_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "pool":
            path_list = [
                ("Pools", url_for("pools_page.pools_page")),
                (f"Pool {id}", url_for("pools_page.pool_page", pool_id=id)),
                (f"Library {library.id}", ""),
            ]
        elif page == "lab_prep":
            path_list = [
                ("Lab Preps", url_for("lab_preps_page.lab_preps_page")),
                (f"Lab Prep {id}", url_for("lab_preps_page.lab_prep_page", lab_prep_id=id)),
                (f"Library {library.id}", ""),
            ]

    library_form = forms.models.LibraryForm(library=library)

    return render_template(
        "library_page.html",
        library=library,
        path_list=path_list,
        library_form=library_form,
    )
