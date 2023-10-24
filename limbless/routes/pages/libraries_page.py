from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from ... import db, forms, logger
from ...core import DBSession
from ...categories import UserRole, HttpResponse

libraries_page_bp = Blueprint("libraries_page", __name__)


@libraries_page_bp.route("/libraries")
@login_required
def libraries_page():
    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            libraries = session.get_libraries(limit=20, user_id=current_user.id, sort_by="id", reversed=True)
            n_pages = int(session.get_num_libraries(user_id=current_user.id) / 20)
        else:
            libraries = session.get_libraries(limit=20, user_id=None, sort_by="id", reversed=True)
            n_pages = int(session.get_num_libraries(user_id=None) / 20)

    return render_template(
        "libraries_page.html",
        libraries=libraries,
        index_kit_results=db.common_kits,
        library_form=forms.LibraryForm(),
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
        
        library.samples = library.samples

    library_form = forms.LibraryForm()
    library_form.name.data = library.name
    library_form.library_type.data = str(library.library_type_id)
    library_form.index_kit.data = library.index_kit_id
    library_form.is_premade_library.data = not library.is_raw_library

    available_samples = db.db_handler.query_samples_for_library(
        word="", exclude_library_id=library_id, user_id=current_user.id
    )

    index_form = forms.create_index_form(library)

    with DBSession(db.db_handler) as session:
        for sample in library.samples:
            sample.indices = session.get_sample_indices_from_library(sample.id, library.id)

    return render_template(
        "library_page.html",
        available_samples=available_samples,
        library=library,
        index_form=index_form,
        available_adapters=db.db_handler.query_adapters(word="", index_kit_id=library.index_kit_id),
        selected_kit=library.index_kit,
        library_form=library_form,
        table_form=forms.TableForm(),
    )
