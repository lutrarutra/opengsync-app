from flask import Blueprint, redirect, url_for, render_template, flash, request
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms
from .... import LibraryType
from ....core import DBSession


libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/libraries/")


@login_required
@libraries_htmx.route("get/<int:page>", methods=["GET"])
def get(page):
    n_pages = int(db.db_handler.get_num_libraries() / 20)

    page = min(page, n_pages)

    libraries = db.db_handler.get_libraries(limit=20, offset=20 * page)

    return make_response(
        render_template(
            "components/tables/library.html",
            libraries=libraries,
            n_pages=n_pages, active_page=page
        ), push_url=False
    )


@login_required
@libraries_htmx.route("create/<int:run_id>", methods=["POST"])
def create(run_id):
    run = db.db_handler.get_run(run_id)
    if not run:
        return redirect("/runs")

    library_form = forms.LibraryForm()

    if not library_form.validate_on_submit():
        template = render_template(
            "forms/library.html", run_form=library_form
        )
        return make_response(
            template, push_url=False
        )

    library = db.db_handler.create_library(
        name=library_form.name.data,
        library_type=library_form.library_type.data,
    )
    db.db_handler.link_run_library(run_id, library.id)

    logger.debug(f"Created library '{library.name}'.")
    flash(f"Created library '{library.name}'.", "success")

    return make_response(
        redirect=url_for("libraries_page.library_page", library_id=library.id),
    )


@login_required
@libraries_htmx.route("edit/<int:library_id>", methods=["POST"])
def edit(library_id):
    library = db.db_handler.get_library(library_id)
    if not library:
        return redirect("/libraries")

    library_form = forms.LibraryForm()

    if not library_form.validate_on_submit():
        if (
            "Library name already exists." in library_form.name.errors and
            library_form.name.data == library.name
        ):
            library_form.name.errors.remove("Library name already exists.")
        else:
            template = render_template(
                "forms/library.html",
                library_form=library_form,
                library_id=library_id,
                selected_kit=library.index_kit,
            )
            return make_response(
                template, push_url=False
            )

    try:
        library_type_id = int(library_form.library_type.data)
        library_type = LibraryType.get(library_type_id)
    except ValueError:
        library_type = None

    library = db.db_handler.update_library(
        library_id=library_id,
        name=library_form.name.data,
        library_type=library_type,
        index_kit_id=library_form.index_kit.data,
    )
    logger.debug(f"Updated library '{library.name}'.")
    flash(f"Updated library '{library.name}'.", "success")

    return make_response(
        redirect=url_for("libraries_page.library_page", library_id=library.id),
    )


@login_required
@libraries_htmx.route("query", methods=["GET"])
def query():
    query = request.args.get("query")

    if not query:
        template = render_template(
            "components/tables/library.html"
        )
        return make_response(
            template, push_url=False
        )

    template = render_template(
        "components/tables/library.html"
    )
    return make_response(
        template, push_url=False
    )


@login_required
@libraries_htmx.route("<int:library_id>/add_sample")
def add_sample(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        logger.warning(f"Unknown library id '{library_id}'")
        return redirect("/libraries")

    if library.library_type in [LibraryType.SC_RNA, LibraryType.SN_RNA]:
        index_form = forms.DualIndexForm()
    else:
        assert False

    selected_adapter = index_form.adapter.data
    selected_sample_id = index_form.sample.data

    if selected_sample_id is not None:
        if (selected_sample := db.db_handler.get_sample(selected_sample_id)) is None:
            logger.warning(f"Unknown sample id '{selected_sample_id}'")
            return make_response(redirect("/libraries"))
    else:
        selected_sample = None

    if not index_form.validate_on_submit():
        logger.debug(index_form.errors)
        template = render_template(
            "forms/index_forms/dual_index_form.html",
            library=library,
            index_form=index_form,
            available_samples=[sample.to_search_result() for sample in db.db_handler.get_user_samples(2)],
            adapters=db.db_handler.get_adapters_from_kit(library.index_kit_id),
            selected_adapter=selected_adapter,
            selected_sample=selected_sample
        )

        return make_response(template)

    # TODO: check if sample is already in the library
    with DBSession(db.db_handler) as session:
        seq_index_id = index_form.index_i7_id.data
        session.link_library_sample(
            library_id=library.id,
            sample_id=selected_sample.id,
            seq_index_id=seq_index_id,
        )

        seq_index_id = index_form.index_i5_id.data
        session.link_library_sample(
            library_id=library.id,
            sample_id=selected_sample.id,
            seq_index_id=seq_index_id,
        )

    logger.debug(f"Added sample '{selected_sample}' to library '{library_id}'")
    flash(f"Added sample '{selected_sample.name}' to library '{library.name}'.", "success")

    return make_response(
        redirect=url_for(
            "libraries_page.library_page", library_id=library.id
        )
    )
