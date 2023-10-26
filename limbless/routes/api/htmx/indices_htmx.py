from typing import Optional

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms, models
from ....core import DBSession
from ....categories import LibraryType, HttpResponse

indices_htmx = Blueprint("indices_htmx", __name__, url_prefix="/api/indices/")


@indices_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"

    if sort_by not in models.SeqIndex.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        n_pages = int(session.get_num_seqindices() / 20)
        page = min(page, n_pages)
        indices = session.get_seqindices(limit=20, offset=20 * page, sort_by=sort_by, reversed=reversed)

    return make_response(
        render_template(
            "components/tables/index.html", indices=indices,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order
        ), push_url=False
    )


@indices_htmx.route("query_index_kits", methods=["POST"])
@login_required
def query_index_kits():
    library_type_id: Optional[int] = None
    
    if (raw_library_type_id := request.form.get("library_type")) is None:
        logger.debug("No library type id provided with POST request")
        return abort(HttpResponse.BAD_REQUEST.value.id)

    try:
        library_type_id = int(raw_library_type_id)
    except ValueError:
        logger.debug(f"Invalid library type '{raw_library_type_id}' id provided with POST request")
        return abort(HttpResponse.BAD_REQUEST.value.id)

    field_name = next(iter(request.form.keys()))
    word = request.form.get(field_name)

    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if library_type_id is not None:
        library_type = LibraryType.get(library_type_id)
    else:
        library_type = None

    results = db.db_handler.query_index_kit(word, library_type=library_type)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@indices_htmx.route("query/<int:index_kit_id>", methods=["POST"], defaults={"exclude_library_id": None})
@indices_htmx.route("query_seq_adapters/<int:index_kit_id>/<int:exclude_library_id>", methods=["POST"])
@login_required
def query_seq_adapters(index_kit_id: int, exclude_library_id: Optional[int] = None):
    field_name = next(iter(request.form.keys()))
    
    if (word := request.form.get(field_name)) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    # TODO: add exclude_library_id to query_adapters
    results = db.db_handler.query_adapters(
        word, index_kit_id=index_kit_id
    )

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@indices_htmx.route("select_indices/<int:library_id>", methods=["POST"])
@login_required
def select_indices(library_id: int):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

    logger.debug(request.form)

    index_form = forms.IndexForm()
    if (selected_adapter_id := index_form.adapter.data) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if (selected_sample_id := index_form.sample.data) is not None:
        with DBSession(db.db_handler) as session:
            selected_sample = session.get_sample(selected_sample_id)
            logger.debug(selected_sample_id)
            logger.debug(library_id)
            if session.is_sample_in_library(selected_sample_id, library.id):
                form = "forms/edit-index.html"
            else:
                form = "forms/index.html"
    else:
        selected_sample = None
        form = "forms/index.html"

    logger.debug(form)

    selected_adapter = db.db_handler.get_adapter(selected_adapter_id)
    index_form.adapter.data = selected_adapter_id

    for i, entry in enumerate(index_form.indices.entries):
        entry.index_seq_id.data = selected_adapter.indices[i].id
        entry.sequence.data = selected_adapter.indices[i].sequence

    return make_response(
        render_template(
            form,
            library=library, sample=selected_sample,
            index_form=index_form,
            selected_adapter=selected_adapter,
            selected_sample=selected_sample
        )
    )
