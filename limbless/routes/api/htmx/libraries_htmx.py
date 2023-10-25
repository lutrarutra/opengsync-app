from typing import Optional
from io import StringIO

import pandas as pd
from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, logger, forms, LibraryType, models, tools
from ....core import DBSession, exceptions
from ....categories import UserRole, HttpResponse

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/libraries/")


@libraries_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"

    if sort_by not in models.Library.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            libraries = session.get_libraries(limit=20, user_id=current_user.id, sort_by=sort_by, reversed=reversed)
            n_pages = int(session.get_num_libraries(user_id=current_user.id) / 20)
        else:
            libraries = session.get_libraries(limit=20, user_id=None, sort_by=sort_by, reversed=reversed)
            n_pages = int(session.get_num_libraries(user_id=None) / 20)

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


@libraries_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.args.keys()), None)
    query = request.args.get(field_name, "")

    if current_user.role_type == UserRole.CLIENT:
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
            
            if library.is_raw_library:
                session.link_library_sample(
                    library_id=library.id,
                    sample_id=sample.id,
                    seq_index_id=None,
                )
            else:
                adapter = db.db_handler.get_adapter_by_name(
                    index_kit_id=library.index_kit_id,
                    name=adapter
                )

                for index in adapter.indices:
                    session.link_library_sample(
                        library_id=library.id,
                        sample_id=sample.id,
                        seq_index_id=index.id,
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