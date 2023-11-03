from flask import Blueprint, render_template, abort, url_for, request
from flask_login import login_required, current_user

from ... import db, forms, logger, PAGE_LIMIT
from ...core import DBSession
from ...categories import UserRole, HttpResponse

libraries_page_bp = Blueprint("libraries_page", __name__)


@libraries_page_bp.route("/libraries")
@login_required
def libraries_page():
    with DBSession(db.db_handler) as session:
        if not current_user.is_insider():
            libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT, user_id=current_user.id, sort_by="id", descending=True)
        else:
            libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT, user_id=None, sort_by="id", descending=True)

    library_form = forms.LibraryForm()
    library_form.library_contact_email.data = current_user.email
    library_form.library_contact_name.data = current_user.name

    return render_template(
        "libraries_page.html",
        libraries=libraries,
        index_kit_results=db.common_kits,
        library_form=library_form,
        n_pages=n_pages, active_page=0,
        current_sort="id", current_sort_order="desc"
    )


@libraries_page_bp.route("/libraries/<int:library_id>")
@login_required
def library_page(library_id):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        access = session.get_user_library_access(current_user.id, library_id)
        if access is None:
            return abort(HttpResponse.FORBIDDEN.value.id)
        
        samples = library.samples
        if not library.is_raw_library():
            for sample in samples:
                sample.indices = session.get_sample_indices_from_library(sample.id, library.id)

    library_form = forms.LibraryForm()
    library_form.name.data = library.name
    library_form.library_type.data = str(library.library_type_id)
    library_form.index_kit.data = library.index_kit_id
    library_form.is_premade_library.data = not library.is_raw_library()

    available_samples = db.db_handler.query_samples(
        word="", exclude_library_id=library_id, user_id=current_user.id
    )

    index_form = forms.create_index_form(library)

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

    return render_template(
        "library_page.html",
        available_samples=available_samples,
        library=library,
        samples=library.samples,
        path_list=path_list,
        index_form=index_form,
        available_adapters=db.db_handler.query_adapters(word="", index_kit_id=library.index_kit_id),
        selected_kit=library.index_kit,
        library_form=library_form,
        table_form=forms.TableForm(),
    )
