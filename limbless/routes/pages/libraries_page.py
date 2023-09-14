from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from ... import db, forms, LibraryType, logger
from ...core import DBSession
from ...categories import UserRole

libraries_page_bp = Blueprint("libraries_page", __name__)


@libraries_page_bp.route("/libraries")
@login_required
def libraries_page():
    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            libraries = session.get_libraries(limit=20, user_id=current_user.id)
            n_pages = int(session.get_num_libraries(user_id=current_user.id) / 20)
        else:
            libraries = session.get_libraries(limit=20, user_id=None)
            n_pages = int(session.get_num_libraries(user_id=None) / 20)

    return render_template(
        "libraries_page.html",
        libraries=libraries,
        index_kit_results=db.common_kits,
        library_form=forms.LibraryForm(),
        n_pages=n_pages, active_page=0
    )


@libraries_page_bp.route("/libraries/<int:library_id>")
@login_required
def library_page(library_id):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(404)

        access = session.get_user_library_access(current_user.id, library_id)
        if access is None:
            return abort(403)

        library.samples = session.get_library_samples(library.id)

    library_form = forms.LibraryForm()
    library_form.name.data = library.name
    library_form.library_type.data = str(library.library_type_id)
    library_form.index_kit.data = library.index_kit_id

    library_sample_ids = [s.id for s in library.samples]
    available_samples = [sample.to_search_result() for sample in db.db_handler.get_user_samples(2) if sample.id not in library_sample_ids]

    index_form = forms.create_index_form(library.library_type)
    index_form_html = render_template(
        "forms/index.html",
        library=library,
        index_form=index_form,
        available_samples=available_samples,
        adapters=db.db_handler.get_adapters_from_kit(library.index_kit_id),
    )

    return render_template(
        "library_page.html",
        library=library,
        selected_kit=library.index_kit,
        library_form=library_form,
        index_form=index_form_html,
        show_indices=library.library_type != LibraryType.RAW,
    )
