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

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/pools/")


@libraries_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page
    logger.debug(sort_by)

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

    logger.debug(template)
    return make_response(
        render_template(
            template, libraries=libraries,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order,
            **context
        ), push_url=False
    )


@libraries_htmx.route("create", methods=["POST"])
@login_required
def create():
    library_form = forms.LibraryForm()

    validated, library_form = library_form.custom_validate(db.db_handler, current_user.id)

    if (index_kit_id := library_form.index_kit.data) is not None:
        if (index_kit := db.db_handler.get_index_kit(index_kit_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
    else:
        index_kit = None

    if not validated:
        return make_response(
            render_template(
                "forms/library.html",
                library_form=library_form,
                index_kit_results=db.common_kits,
                selected_kit=index_kit,
            ), push_url=False
        )

    library_type = LibraryType.get(int(library_form.library_type.data))

    if library_form.is_premade_library.data:
        if library_form.current_user_is_library_contact:
            contact = db.db_handler.create_contact(
                name=current_user.name,
                email=current_user.email,
                phone=library_form.library_contact_phone.data,
            )
        else:
            contact = db.db_handler.create_contact(
                name=library_form.library_contact_name.data,
                email=library_form.library_contact_email.data,
                phone=library_form.library_contact_phone.data,
            )
    else:
        contact = None

    library = db.db_handler.create_library(
        name=library_form.name.data,
        library_type=library_type,
        index_kit_id=index_kit_id,
        owner_id=current_user.id,
        contact_id=contact.id if contact is not None else None,
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
        if not library.is_editable():
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


@libraries_htmx.route("<int:library_id>/add_sample", methods=["POST"])
@login_required
def add_sample(library_id: int):
    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

    index_form = forms.IndexForm()

    if (selected_adapter_id := index_form.adapter.data) is not None:
        selected_adapter = db.db_handler.get_adapter(selected_adapter_id)
    else:
        selected_adapter = None
        
    if (selected_sample_id := index_form.sample.data) is not None:
        selected_sample = db.db_handler.get_sample(selected_sample_id)
    else:
        selected_sample = None
        
    validated, index_form = index_form.custom_validate(library_id, current_user.id, db.db_handler)
    available_samples, _ = db.db_handler.get_samples(user_id=current_user.id)
    if not validated:
        template = render_template(
            "forms/index.html",
            library=library,
            index_form=index_form,
            available_samples=available_samples,
            available_adapters=db.db_handler.query_adapters(word="", index_kit_id=library.index_kit_id),
            selected_adapter=selected_adapter,
            selected_sample=selected_sample
        )

        return make_response(template)
    
    if (selected_sample := db.db_handler.get_sample(selected_sample_id)) is None:
        logger.error(f"Unknown sample id '{selected_sample_id}'")
        return abort(HttpResponse.FORBIDDEN.value.id)

    with DBSession(db.db_handler) as session:
        if library.is_raw_library():
            session.link_library_sample(
                library_id=library.id,
                sample_id=selected_sample.id,
                barcode_id=None,
            )
        else:
            for entry in index_form.barcodes.entries:
                barcode_id = entry.index_seq_id.data
                try:
                    session.link_library_sample(
                        library_id=library.id,
                        sample_id=selected_sample.id,
                        barcode_id=barcode_id,
                    )
                except exceptions.LinkAlreadyExists:
                    logger.error(f"Sample '{selected_sample}' already linked to library '{library.id}' with index '{barcode_id}'")
                    flash(f"Sample '{selected_sample}' already linked to library '{library.id}' with index '{barcode_id}'.", "error")
    
    logger.debug(f"Added sample '{selected_sample}' to library '{library_id}'")
    flash(f"Added sample '{selected_sample.name}' to library '{library.name}'.", "success")

    return make_response(
        redirect=url_for(
            "libraries_page.library_page", library_id=library.id
        )
    )


@libraries_htmx.route("<int:library_id>/remove_sample", methods=["DELETE"])
@login_required
def remove_sample(library_id: int):
    if (sample_id := request.args.get("sample_id")) is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    try:
        sample_id = int(sample_id)
    except ValueError:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    with DBSession(db.db_handler) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        if (sample := session.get_sample(sample_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)
        
        session.unlink_library_sample(library_id=library_id, sample_id=sample_id)

    logger.debug(f"Removed sample '{sample.name}' from library '{library.name}'")
    flash(f"Removed sample '{sample.name}' from library '{library.name}'.", "success")

    return make_response(
        redirect=url_for("libraries_page.library_page", library_id=library.id)
    )


@libraries_htmx.route("<int:library_id>/parse_table", methods=["POST"])
@login_required
def parse_table(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    table_input_form = forms.TableForm()
    validated, table_input_form = table_input_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/library/table.html",
                table_form=table_input_form,
                library=library,
            ), push_url=False
        )

    raw_text, sep = table_input_form.get_data()

    df = pd.read_csv(
        StringIO(raw_text.rstrip()), sep=sep,
        index_col=False, header=0
    )

    library_col_mapping_form = forms.LibraryColMappingForm()
    library_col_mapping_form.data.data = df.to_csv(sep="\t", index=False, header=True)

    columns = df.columns.tolist()
    refs = [key for key, _ in forms.LibraryColSelectForm._fields if key]
    matches = tools.connect_similar_strings(forms.LibraryColSelectForm._fields, columns)

    for i, col in enumerate(columns):
        select_form = forms.LibraryColSelectForm()
        select_form.select_field.label.text = col
        library_col_mapping_form.fields.append_entry(select_form)
        library_col_mapping_form.fields.entries[i].select_field.data = col
        if col in matches.keys():
            library_col_mapping_form.fields.entries[i].select_field.data = matches[col]

    submittable: bool = set(matches.values()) == set(refs)
    
    return make_response(
        render_template(
            "components/popups/library/col_mapping.html",
            columns=columns, submittable=submittable, library=library,
            library_col_mapping_form=library_col_mapping_form,
            data=df.values.tolist(), required_fields=refs,
        )
    )


@libraries_htmx.route("<int:library_id>/map_columns", methods=["POST"])
@login_required
def map_columns(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    library_col_mapping_form = forms.LibraryColMappingForm()
    validated, library_col_mapping_form = library_col_mapping_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/library/col_mapping.html",
                library_col_mapping_form=library_col_mapping_form,
                library=library
            )
        )
    
    df = pd.read_csv(StringIO(library_col_mapping_form.data.data), sep="\t", index_col=False, header=0)
    for i, entry in enumerate(library_col_mapping_form.fields.entries):
        val = entry.select_field.data.strip()
        if not val:
            continue
        df.rename(columns={df.columns[i]: val}, inplace=True)

    refs = [key for key, _ in forms.LibraryColSelectForm._fields if key]
    df = df.loc[:, refs]

    library_sample_select_form = forms.LibrarySampleSelectForm()
    library_samples, errors = library_sample_select_form.parse_library_samples(library_id=library_id, df=df)
    
    return make_response(
        render_template(
            "components/popups/library/library_sample_select.html",
            library_sample_select_form=library_sample_select_form,
            library=library, errors=errors,
            library_samples=library_samples,
        )
    )


@libraries_htmx.route("<int:library_id>/add_samples", methods=["POST"])
@login_required
def add_library_samples_from_table(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    library_sample_select_form = forms.LibrarySampleSelectForm()
    library_samples, errors = library_sample_select_form.parse_library_samples(library_id=library_id)
    validated, library_sample_select_form = library_sample_select_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/library/library_sample_select.html",
                library_sample_select_form=library_sample_select_form,
                library=library, errors=errors,
                library_samples=library_samples,
            ), push_url=False
        )
    
    df = pd.read_csv(StringIO(library_sample_select_form.data.data), sep="\t", index_col=False, header=0)

    if library_sample_select_form.selected_samples.data is None:
        assert False    # This should never happen because of custom validation

    selected_samples_ids = library_sample_select_form.selected_samples.data.removeprefix(",").split(",")
    selected_samples_ids = [int(i) for i in selected_samples_ids if i != ""]
    
    n_added = 0
    with DBSession(db.db_handler) as session:
        for _, row in df.iterrows():
            if row["id"] not in selected_samples_ids:
                continue
            
            sample_id = int(row["id"])
            adapter = row["adapter"]

            if (sample := session.get_sample(sample_id)) is None:
                logger.error(f"Unknown sample id '{sample_id}'")
                continue
            
            if library.is_raw_library():
                session.link_library_sample(
                    library_id=library.id,
                    sample_id=sample.id,
                    barcode_id=None,
                )
            else:
                adapter = db.db_handler.get_adapter_by_name(
                    index_kit_id=library.index_kit_id,
                    name=adapter
                )

                for index in adapter.barcodes:
                    session.link_library_sample(
                        library_id=library.id,
                        sample_id=sample.id,
                        barcode_id=index.id,
                    )
            n_added += 1

    logger.info(f"Added samples from table to library {library.name} (id: {library.id})")
    if n_added == 0:
        flash("No samples added.", "warning")
    elif n_added == len(selected_samples_ids):
        flash(f"Added all ({n_added}) samples to library succesfully.", "success")
    elif n_added < len(selected_samples_ids):
        flash(f"Some samples ({len(selected_samples_ids) - n_added}) could not be added.", "warning")

    return make_response(
        redirect=url_for(
            "libraries_page.library_page",
            library_id=library.id
        )
    )


@libraries_htmx.route("<int:library_id>/restart_form", methods=["GET"])
@login_required
def restart_form(library_id: int):
    if (library := db.db_handler.get_library(library_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    return make_response(
        render_template(
            "components/popups/library/table.html",
            table_form=forms.TableForm(),
            library=library
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