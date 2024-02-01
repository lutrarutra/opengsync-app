from typing import TYPE_CHECKING
from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required

from ... import db, forms, logger, PAGE_LIMIT
from ...core import DBSession
from ...models import User
from ...categories import UserRole, HttpResponse

if TYPE_CHECKING:
    current_user: User = None
else:
    from flask_login import current_user

libraries_page_bp = Blueprint("libraries_page", __name__)


@libraries_page_bp.route("/libraries")
@login_required
def libraries_page():
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT, user_id=current_user.id, sort_by="id", descending=True)
        else:
            libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT, user_id=None, sort_by="id", descending=True)

    library_form = forms.EditLibraryForm()

    return render_template(
        "libraries_page.html",
        libraries=libraries,
        index_kit_results=db.common_kits,
        library_form=library_form,
        libraries_n_pages=n_pages, libraries_active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@libraries_page_bp.route("/libraries/<int:library_id>")
@login_required
def library_page(library_id):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if not current_user.is_insider():
            if library.owner_id != current_user.id:
                return abort(HttpResponse.FORBIDDEN.value.id)

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

    library_edit_form = forms.EditLibraryForm()
    library_edit_form.adapter.data = library.adapter    # TODO: separate adapter for all indices
    library_edit_form.library_type.data = library.type_id
    library_edit_form.index_1.data = library.index_1_sequence
    library_edit_form.index_2.data = library.index_2_sequence
    library_edit_form.index_3.data = library.index_3_sequence
    library_edit_form.index_4.data = library.index_4_sequence

    return render_template(
        "library_page.html",
        library=library,
        path_list=path_list,
        library_edit_form=library_edit_form,
    )
