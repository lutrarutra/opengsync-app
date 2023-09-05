from flask import Blueprint, render_template, redirect
from flask_login import login_required

from ... import db, forms, LibraryType, logger
from ...core import DBSession

libraries_page_bp = Blueprint("libraries_page", __name__)


@libraries_page_bp.route("/libraries")
@login_required
def libraries_page():
    with DBSession(db.db_handler) as session:
        libraries = session.get_libraries()
        n_pages = int(session.get_num_libraries() / 20)

    return render_template(
        "libraries_page.html", libraries=libraries,
        n_pages=n_pages, page=0
    )


@libraries_page_bp.route("/libraries/<int:library_id>")
@login_required
def library_page(library_id):
    with DBSession(db.db_handler) as session:
        library = session.get_library(library_id)
        if not library:
            return redirect("/libraries")

        library.samples = session.get_library_samples(library.id)

    library_form = forms.LibraryForm()
    library_form.name.data = library.name
    library_form.library_type.data = str(library.library_type_id)
    library_form.index_kit.data = library.index_kit_id

    library_sample_ids = [s.id for s in library.samples]
    available_samples = [sample.to_search_result() for sample in db.db_handler.get_user_samples(2) if sample.id not in library_sample_ids]

    if library.library_type in [LibraryType.SC_RNA, LibraryType.SN_RNA]:
        index_form = render_template(
            "forms/index_forms/dual_index_form.html",
            library=library,
            index_form=forms.DualIndexForm(),
            available_samples=available_samples,
            adapters=db.db_handler.get_adapters_from_kit(library.index_kit_id),
        )
    else:
        assert False

    return render_template(
        "library_page.html",
        library=library,

        library_form=library_form,
        common_indexkits=db.common_kits,
        selected_kit=library.index_kit,
        index_form=index_form,

        show_indices=True
    )
