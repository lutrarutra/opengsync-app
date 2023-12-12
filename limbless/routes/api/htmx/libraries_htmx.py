from typing import Optional, TYPE_CHECKING
from io import StringIO

import pandas as pd
from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required

from .... import db, logger, forms, models, tools, PAGE_LIMIT
from ....core import DBSession, exceptions
from ....core.DBHandler import DBHandler
from ....categories import UserRole, HttpResponse, LibraryType

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/libraries/")


@libraries_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Library.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    libraries: list[models.Library] = []
    context = {}

    if (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-library.html"
        try:
            seq_request_id = int(seq_request_id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            libraries, n_pages = session.get_libraries(
                limit=PAGE_LIMIT, offset=offset, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending
            )
            context["seq_request"] = seq_request
    elif (experiment_id := request.args.get("experiment_id", None)) is not None:
        template = "components/tables/experiment-library.html"
        try:
            experiment_id = int(experiment_id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            libraries, n_pages = session.get_libraries(
                limit=PAGE_LIMIT, offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending
            )
            context["experiment"] = experiment
    elif (sample_id := request.args.get("sample_id", None)) is not None:
        template = "components/tables/sample-library.html"
        try:
            sample_id = int(sample_id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (sample := session.get_sample(sample_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            libraries, n_pages = session.get_libraries(
                limit=PAGE_LIMIT, offset=offset, sample_id=sample_id, sort_by=sort_by, descending=descending
            )
            context["sample"] = sample
    else:
        template = "components/tables/library.html"
        with DBSession(db.db_handler) as session:
            if not current_user.is_insider():
                libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT, offset=offset, user_id=current_user.id, sort_by=sort_by, descending=descending)
            else:
                libraries, n_pages = session.get_libraries(limit=PAGE_LIMIT, offset=offset, user_id=None, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            template, libraries=libraries,
            libraries_n_pages=n_pages, libraries_active_page=page,
            libraries_current_sort=sort_by, libraries_current_sort_order=order,
            **context
        ), push_url=False
    )


@libraries_htmx.route("edit/<int:library_id>", methods=["POST"])
@login_required
def edit(library_id):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        if not library.is_editable():
            return abort(HttpResponse.FORBIDDEN.value.id)

    edit_library_form = forms.EditLibraryForm()
    validated, edit_library_form = edit_library_form.custom_validate(db.db_handler, current_user.id, library_id=library_id)

    if not validated:
        logger.debug("Not valid")
        logger.debug(edit_library_form.errors)
        return make_response(
            render_template(
                "forms/library.html",
                edit_library_form=edit_library_form,
            ), push_url=False
        )

    try:
        library_type_id = int(edit_library_form.library_type.data)
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


@libraries_htmx.route("<int:library_id>/edit-adapter-form/<int:sample_id>", methods=["GET"])
@login_required
def get_edit_library_sample_adapter_form(library_id: int, sample_id: int):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if (sample := session.get_sample(sample_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
    
        if sample_id not in [s.id for s in library.samples]:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        seq_barcodes = db.db_handler.get_sample_barcodes_from_library(
            sample_id=sample_id, library_id=library_id
        )
        
    index_form = forms.create_index_form(library)
    index_form.sample.data = sample_id
    index_form.adapter.data = seq_barcodes[0].adapter.name
    
    for i, index in enumerate(seq_barcodes):
        if i < len(index_form.barcodes.entries):
            index_form.barcodes.entries[i].sequence.data = index.sequence
            index_form.barcodes.entries[i].index_seq_id.data = index.id

    return make_response(
        render_template(
            "forms/edit-index.html",
            index_form=index_form,
            library=library, sample=sample,
            selected_adapter=seq_barcodes[0].adapter,
        ), push_url=False
    )


@libraries_htmx.route("<int:library_id>/edit-adapter", methods=["POST"])
@login_required
def edit_adapter(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    index_form = forms.IndexForm()
    sample_id = index_form.sample.data

    if sample_id is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if (sample := db.db_handler.get_sample(sample_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    validated, index_form = index_form.custom_validate(library_id, current_user.id, db.db_handler, action="update")

    if (adapter_id := index_form.adapter.data) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if (adapter := db.db_handler.get_adapter(adapter_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not validated:
        logger.debug("Not valid")
        return make_response(
            render_template(
                "forms/edit-index.html",
                index_form=index_form,
                library=library, sample=sample,
                selected_adapter=adapter
            ), push_url=False
        )
    
    db.db_handler.unlink_library_sample(library_id=library_id, sample_id=sample_id)

    with DBSession(db.db_handler) as session:
        for index in adapter.barcodes:
            session.link_library_sample(
                library_id=library.id,
                sample_id=sample.id,
                barcode_id=index.id,
            )

    logger.debug(f"Edited adapter for sample '{sample.name}' in library '{library.name}'")
    flash(f"Edited adapter for sample '{sample.name}' in library '{library.name}'", "success")

    return make_response(
        redirect=url_for(
            "libraries_page.library_page", library_id=library.id
        )
    )


@libraries_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.args.keys()), None)
    query = request.args.get(field_name, "")

    if not current_user.is_insider():
        results = db.db_handler.query_libraries(query, current_user.id)
    else:
        results = db.db_handler.query_libraries(query)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name,
        ), push_url=False
    )


@libraries_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if (word := request.form.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    def __get_libraries(
        session: DBHandler, word: str | int, field_name: str, sample_id: Optional[int] = None,
        seq_request_id: Optional[int] = None, experiment_id: Optional[int] = None, user_id: Optional[int] = None
    ) -> list[models.Library]:
        libraries: list[models.Library] = []
        if field_name == "name":
            libraries = session.query_libraries(
                str(word), user_id=user_id, seq_request_id=seq_request_id,
                experiment_id=experiment_id, sample_id=sample_id
            )
        elif field_name == "id":
            try:
                _id = int(word)
                if (library := session.get_library(_id)) is not None:
                    if seq_request_id is not None:
                        if seq_request_id in [sr.id for sr in library.seq_requests]:
                            libraries = [library]
                    elif experiment_id is not None:
                        if experiment_id in [e.id for e in library.experiments]:
                            libraries = [library]
                    elif sample_id is not None:
                        if sample_id in [s.id for s in library.samples]:
                            libraries = [library]
                    elif user_id is not None:
                        if library.owner_id == user_id:
                            libraries = [library]
                    else:
                        libraries = [library]
            except ValueError:
                pass
        else:
            assert False    # This should never happen

        return libraries
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-library.html"
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_library(seq_request_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
                
            libraries = __get_libraries(session, word, field_name, seq_request_id=seq_request_id)
        context["seq_request"] = seq_request
    elif (seq_request_id := request.args.get("experiment_id", None)) is not None:
        template = "components/tables/experiment-library.html"
        try:
            experiment_id = int(seq_request_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with DBSession(db.db_handler) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
                
            libraries = __get_libraries(session, word, field_name, experiment_id=experiment_id)
            context["experiment"] = experiment
    elif (sample_id := request.args.get("sample_id", None)) is not None:
        template = "components/tables/sample-library.html"
        try:
            sample_id = int(sample_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with DBSession(db.db_handler) as session:
            if (sample := session.get_sample(sample_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
                
            libraries = __get_libraries(session, word, field_name, sample_id=sample_id)
            context["sample"] = sample
    else:
        template = "components/tables/library.html"

        with DBSession(db.db_handler) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            libraries = __get_libraries(session, word, field_name, user_id=user_id)

    return make_response(
        render_template(
            template,
            current_query=word, field_name=field_name,
            libraries=libraries, **context
        ), push_url=False
    )


@libraries_htmx.route("select_library_contact", methods=["POST"])
@login_required
def select_library_contact():
    library_form = forms.LibraryForm()

    if (library_contact_insider_user_id := library_form.library_contact_insider.data) is not None:
        if (user := db.db_handler.get_user(library_contact_insider_user_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        library_form.current_user_is_library_contact.data = False
    elif library_form.current_user_is_library_contact.data:
        user = current_user
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)
        
    library_form.library_contact_name.data = user.name
    library_form.library_contact_email.data = user.email
    library_form.current_user_is_library_contact.data = current_user.id == user.id

    if (index_kit_id := library_form.index_kit.data) is not None:
        if (index_kit := db.db_handler.get_index_kit(index_kit_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
    else:
        index_kit = None

    return make_response(
        render_template(
            "forms/library.html",
            library_form=library_form,
            index_kit_results=db.common_kits,
            selected_kit=index_kit,
            selected_user=user
        ), push_url=False
    )