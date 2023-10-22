from typing import Optional

from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms, LibraryType, models
from ....core import DBSession, exceptions
from ....categories import UserRole, HttpResponse

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/libraries/")


@libraries_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "asc")
    reversed = order == "desc"

    if sort_by not in models.Library.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        n_pages = int(session.get_num_libraries() / 20)
        page = min(page, n_pages)
        libraries = session.get_libraries(limit=20, offset=20 * page, sort_by=sort_by, reversed=reversed)

    return make_response(
        render_template(
            "components/tables/library.html",
            libraries=libraries,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order
        ), push_url=False
    )


@libraries_htmx.route("create", methods=["POST"])
@login_required
def create():
    library_form = forms.LibraryForm()

    validated, library_form = library_form.custom_validate(db.db_handler, current_user.id)

    if not validated:
        template = render_template(
            "forms/library.html",
            library_form=library_form,
            index_kit_results=db.common_kits,
            selected_kit_id=library_form.index_kit.data,
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
        owner_id=current_user.id,
    )

    logger.debug(f"Created library '{library.name}'.")
    flash(f"Created library '{library.name}'.", "success")

    return make_response(
        redirect=url_for("libraries_page.library_page", library_id=library.id),
    )


@libraries_htmx.route("edit/<int:library_id>", methods=["POST"])
@login_required
def edit(library_id):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        if not library.is_editable:
            return abort(HttpResponse.FORBIDDEN.value.id)

    library_form = forms.LibraryForm()

    validated, library_form = library_form.custom_validate(db.db_handler, current_user.id, library_id=library_id)

    if not validated:
        logger.debug("Not valid")
        logger.debug(library_form.errors)
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


@libraries_htmx.route("query", methods=["GET"])
@login_required
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


@libraries_htmx.route("<int:library_id>/add_sample", methods=["POST"])
@login_required
def add_sample(library_id: int):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

    index_form = forms.IndexForm()

    selected_adapter = index_form.adapter.data
    selected_sample_id = index_form.sample.data
        
    validated, index_form = index_form.custom_validate(library_id, current_user.id, db.db_handler)

    if not validated:
        template = render_template(
            "forms/index.html",
            library=library,
            index_form=index_form,
            available_samples=[sample.to_search_result() for sample in current_user.samples],
            available_adapters=db.db_handler.query_adapters(word="", index_kit_id=library.index_kit_id),
            selected_adapter=selected_adapter,
            selected_sample=db.db_handler.get_sample(selected_sample_id)
        )

        return make_response(template)
    
    if (selected_sample := db.db_handler.get_sample(selected_sample_id)) is None:
        logger.error(f"Unknown sample id '{selected_sample_id}'")
        return abort(HttpResponse.FORBIDDEN.value.id)

    with DBSession(db.db_handler) as session:
        if library.is_raw_library:
            session.link_library_sample(
                library_id=library.id,
                sample_id=selected_sample.id,
                seq_index_id=None,
            )
        else:
            for entry in index_form.indices.entries:
                seq_index_id = entry.index_seq_id.data
                try:
                    session.link_library_sample(
                        library_id=library.id,
                        sample_id=selected_sample.id,
                        seq_index_id=seq_index_id,
                    )
                except exceptions.LinkAlreadyExists:
                    logger.error(f"Sample '{selected_sample}' already linked to library '{library.id}' with index '{seq_index_id}'")
                    flash(f"Sample '{selected_sample}' already linked to library '{library.id}' with index '{seq_index_id}'.", "error")
    
    logger.debug(f"Added sample '{selected_sample}' to library '{library_id}'")
    flash(f"Added sample '{selected_sample.name}' to library '{library.name}'.", "success")

    return make_response(
        redirect=url_for(
            "libraries_page.library_page", library_id=library.id
        )
    )
