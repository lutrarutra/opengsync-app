from flask import Blueprint, redirect, url_for, render_template, flash, request
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms, LibraryType, UserResourceRelation
from ....core import DBSession, exceptions
from ....categories import UserRole


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
@libraries_htmx.route("create", methods=["POST"])
def create():
    library_form = forms.LibraryForm()

    # if raw library (i.e. no index kit)
    validated_indexkit = True
    if library_form.library_type.data == "0":
        if library_form.index_kit.data is not None:
            validated_indexkit = False

    if not library_form.validate_on_submit() or not validated_indexkit:
        if not validated_indexkit:
            library_form.index_kit.errors.append("Raw library cannot have an index kit.")

        selected_kit = db.db_handler.get_indexkit(library_form.index_kit.data)

        template = render_template(
            "forms/library.html",
            library_form=library_form,
            index_kit_results=db.common_kits,
            selected_kit=selected_kit,
        )
        return make_response(
            template, push_url=False
        )

    library_type = LibraryType.get(int(library_form.library_type.data))

    logger.debug(library_form.index_kit.data)
    library = db.db_handler.create_library(
        name=library_form.name.data,
        library_type=library_type,
        index_kit_id=library_form.index_kit.data,
    )

    db.db_handler.link_library_user(
        library_id=library.id,
        user_id=current_user.id,
        relation=UserResourceRelation.OWNER
    )

    logger.debug(f"Created library '{library.name}'.")
    flash(f"Created library '{library.name}'.", "success")

    return make_response(
        redirect=url_for("libraries_page.library_page", library_id=library.id),
    )


@ login_required
@ libraries_htmx.route("edit/<int:library_id>", methods=["POST"])
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
    field_name = next(iter(request.args.keys()))
    query = request.args.get(field_name)
    assert query is not None

    if current_user.role_type == UserRole.CLIENT:
        results = db.db_handler.query_libraries(query, current_user.id)
    else:
        results = db.db_handler.query_libraries(query)

    if not query:
        return make_response(
            render_template(
                "components/tables/library.html"
            ), push_url=False
        )

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@login_required
@libraries_htmx.route("<int:library_id>/add_sample", methods=["POST"])
def add_sample(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        logger.warning(f"Unknown library id '{library_id}'")
        return redirect("/libraries")

    index_form = forms.IndexForm()

    selected_adapter = index_form.adapter.data
    selected_sample_id = index_form.sample.data

    selected_sample = None
    if selected_sample_id is not None:
        if (selected_sample := db.db_handler.get_sample(selected_sample_id)) is None:
            logger.warning(f"Unknown sample id '{selected_sample_id}'")
            return make_response(redirect("/libraries"))
        
    valid_adapter = True
    if library.library_type != LibraryType.RAW:
        if selected_adapter is None:
            valid_adapter = False

    if not index_form.validate_on_submit() or not valid_adapter:
        if not valid_adapter:
            index_form.adapter.errors.append("Adapter required.")
        logger.debug(index_form.errors)
        template = render_template(
            "forms/index.html",
            library=library,
            index_form=index_form,
            available_samples=[sample.to_search_result() for sample in db.db_handler.get_user_samples(2)],
            adapters=db.db_handler.get_adapters_from_kit(library.index_kit_id),
            selected_adapter=selected_adapter,
            selected_sample=selected_sample
        )

        return make_response(template)

    # TODO: check if sample is already in the library
    if library.library_type != LibraryType.RAW:
        with DBSession(db.db_handler) as session:
            for entry in index_form.indices.entries:
                seq_index_id = entry.index_seq_id.data
                try:
                    session.link_library_sample(
                        library_id=library.id,
                        sample_id=selected_sample.id,
                        seq_index_id=seq_index_id,
                    )
                except exceptions.LinkAlreadyExists:
                    logger.warning(f"Sample '{selected_sample}' already linked to library '{library.id}' with index '{seq_index_id}'")
                    flash(f"Sample '{selected_sample}' already linked to library '{library.id}' with index '{seq_index_id}'.", "warning")
    else:
        with DBSession(db.db_handler) as session:
            try:
                session.link_library_sample(
                    library_id=library.id,
                    sample_id=selected_sample.id,
                    seq_index_id=None,
                )
            except exceptions.LinkAlreadyExists:
                logger.warning(f"Sample '{selected_sample}' already linked to library '{library.id}'")
                flash(f"Sample '{selected_sample}' already linked to library '{library.id}''.", "warning")

    logger.debug(f"Added sample '{selected_sample}' to library '{library_id}'")
    flash(f"Added sample '{selected_sample.name}' to library '{library.name}'.", "success")

    return make_response(
        redirect=url_for(
            "libraries_page.library_page", library_id=library.id
        )
    )
