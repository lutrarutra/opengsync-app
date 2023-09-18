from typing import Optional

from flask import Blueprint, render_template, request, abort, url_for
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms
from ....core import DBSession
from ....categories import LibraryType

indices_htmx = Blueprint("indices_htmx", __name__, url_prefix="/api/indices/")


@login_required
@indices_htmx.route("query_index_kits", methods=["POST"])
def query_index_kits():
    library_type_id: Optional[int] = None
    raw_library_type_id = request.form.get("library_type")

    try:
        library_type_id = int(raw_library_type_id)
    except KeyError:
        logger.debug("No library type id provided with POST request")
    except ValueError:
        logger.debug(f"Invalid library type '{raw_library_type_id}' id provided with POST request")
        return abort(400)
    
    field_name = next(iter(request.form.keys()))
    word = request.form.get(field_name)

    if word is None:
        return abort(400)

    if library_type_id is not None:
        library_type = LibraryType.get(library_type_id)
    else:
        library_type = None

    results = db.db_handler.query_indexkit(word, library_type=library_type)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@login_required
@indices_htmx.route("query/<int:index_kit_id>", methods=["POST"], defaults={"exclude_library_id": None})
@indices_htmx.route("query_seq_adapters/<int:index_kit_id>/<int:exclude_library_id>", methods=["POST"])
def query_seq_adapters(index_kit_id: int, exclude_library_id: Optional[int] = None):
    field_name = next(iter(request.form.keys()))
    word = request.form.get(field_name)

    if word is None:
        return abort(400)

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


@login_required
@indices_htmx.route("select_indices/<int:library_id>", methods=["POST"])
def select_indices(library_id: int):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(404)
        if (user := session.get_user(current_user.id)) is None:
            return abort(404)
        
        user.samples = user.samples

    index_form = forms.IndexForm()
    selected_adapter = index_form.adapter.data
    selected_sample_id = index_form.sample.data

    indices = session.get_seqindices_by_adapter(selected_adapter)
    selected_sample = db.db_handler.get_sample(selected_sample_id)


    for i, entry in enumerate(index_form.indices.entries):
        entry.index_seq_id.data = indices[i].id
        entry.sequence.data = indices[i].sequence



    return make_response(
        render_template(
            "forms/index.html",
            library=library,
            index_form=index_form,
            selected_adapter=selected_adapter,
            selected_sample=selected_sample
        )
    )
