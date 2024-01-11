import os
from io import StringIO
from typing import Optional, Any, TYPE_CHECKING

from flask import Blueprint, redirect, url_for, render_template, flash, request, abort, Response, send_file, current_app
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename

import pandas as pd

from .... import db, logger, forms, models, PAGE_LIMIT
from ....core import DBSession
from ....categories import UserRole, HttpResponse, LibraryType, BarcodeType

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user


seq_request_form_htmx = Blueprint("seq_request_form_htmx", __name__, url_prefix="/api/samples/")


# Template sample annotation sheet
@seq_request_form_htmx.route("download_template/<string:type>", methods=["GET"])
@login_required
def download_template(type: str):
    if type == "raw":
        name = "sas_raw_libraries.tsv"
    elif type == "premade":
        name = "sas_premade_libraries.tsv"
    else:
        return abort(HttpResponse.NOT_FOUND.value.id)

    path = os.path.join(
        current_app.root_path,
        "static", "resources", "templates", name
    )

    return send_file(path, mimetype="text/csv", as_attachment=True, download_name=name)


# Template sequencing authorization form
@seq_request_form_htmx.route("seq_auth_form/download", methods=["GET"])
@login_required
def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"

    path = os.path.join(
        current_app.root_path,
        "static", "resources", "templates", name
    )

    return send_file(path, mimetype="pdf", as_attachment=True, download_name=name)


# 0. Restart form
@seq_request_form_htmx.route("<int:seq_request_id>/restart_form", methods=["GET"])
@login_required
def restart_form(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    return make_response(
        render_template(
            "components/popups/seq_request/step-1.html",
            table_form=forms.TableForm(),
            seq_request=seq_request
        ), push_url=False
    )


# 1. Input sample annotation sheet
@seq_request_form_htmx.route("<int:seq_request_id>/parse_table", methods=["POST"])
@login_required
def parse_table(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    table_input_form = forms.TableForm()
    validated, table_input_form = table_input_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/step-1.html",
                table_form=table_input_form, seq_request=seq_request
            ), push_url=False
        )
    
    try:
        df = table_input_form.parse()
    except pd.errors.ParserError as e:
        table_input_form.file.errors = (str(e),)
            
        return make_response(
            render_template(
                "components/popups/seq_request/step-1.html",
                table_form=table_input_form, seq_request=seq_request
            ), push_url=False
        )
        
    table_col_form = forms.SampleColTableForm()
    context = table_col_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/seq_request/step-2.html",
            sample_table_form=table_col_form,
            data=df.values.tolist(),
            seq_request=seq_request,
            **context
        ), push_url=False
    )


# 2. Map columns to sample features
@seq_request_form_htmx.route("<int:seq_request_id>/map_columns", methods=["POST"])
@login_required
def map_columns(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    sample_table_form = forms.SampleColTableForm()
    context = sample_table_form.prepare()
    validated, sample_table_form = sample_table_form.custom_validate()
    
    if not validated:
        # TODO: show errors
        return make_response(
            render_template(
                "components/popups/seq_request/step-2.html",
                sample_table_form=sample_table_form,
                data=sample_table_form.get_df().values.tolist(),
                seq_request=seq_request,
                **context
            ),
            push_url=False
        )

    df = sample_table_form.parse()
    project_mapping_form = forms.ProjectMappingForm(formdata=None)
    context = project_mapping_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/seq_request/step-3.html",
            project_mapping_form=project_mapping_form,
            seq_request=seq_request, **context
        ), push_url=False
    )


# 3. Select project
@seq_request_form_htmx.route("<int:seq_request_id>/project_select", methods=["POST"])
@login_required
def select_project(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    project_mapping_form = forms.ProjectMappingForm()
    validated, project_mapping_form = project_mapping_form.custom_validate(db.db_handler, current_user.id)

    if not validated:
        context = project_mapping_form.prepare()
        return make_response(
            render_template(
                "components/popups/seq_request/step-3.html",
                project_mapping_form=project_mapping_form,
                seq_request=seq_request, **context
            ), push_url=False
        )
    
    df = project_mapping_form.parse(seq_request_id=seq_request_id)

    category_mapping_form = forms.OrganismMappingForm(formdata=None)
    context = category_mapping_form.prepare(seq_request.id, df)

    if df["sample_id"].isna().any():
        # new sample -> map organisms
        return make_response(
            render_template(
                "components/popups/seq_request/step-4.html",
                category_mapping_form=category_mapping_form,
                seq_request=seq_request, **context
            ), push_url=False
        )

    library_mapping_form = forms.LibraryMappingForm()
    context = library_mapping_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/seq_request/step-5.html",
            seq_request=seq_request,
            library_mapping_form=library_mapping_form,
            **context
        )
    )


# 4. Map organisms if new samples
@seq_request_form_htmx.route("<int:seq_request_id>/map_organisms", methods=["POST"])
@login_required
def map_organisms(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    category_mapping_form = forms.OrganismMappingForm()
    validated, category_mapping_form = category_mapping_form.custom_validate(db.db_handler)
    df = category_mapping_form.get_df()
    organisms = sorted(df["organism"].unique())

    if not validated:
        selected = []
        with DBSession(db.db_handler) as session:
            for i, organism in enumerate(organisms):
                category_mapping_form.input_fields.entries[i].raw_category.data = organism
                if category_mapping_form.input_fields.entries[i].category.data:
                    selected_organism = session.get_organism(category_mapping_form.input_fields.entries[i].category.data)
                    selected.append(str(selected_organism))
                else:
                    selected.append("")

        return make_response(
            render_template(
                "components/popups/seq_request/step-4.html",
                category_mapping_form=category_mapping_form,
                categories=organisms, selected=selected,
                seq_request=seq_request
            ), push_url=False
        )

    organism_id_mapping = {}
    
    for i, organism in enumerate(organisms):
        organism_id_mapping[organism] = category_mapping_form.input_fields.entries[i].category.data
    
    df["tax_id"] = df["organism"].map(organism_id_mapping)

    library_mapping_form = forms.LibraryMappingForm()
    context = library_mapping_form.prepare(df)
    return make_response(
        render_template(
            "components/popups/seq_request/step-5.html",
            seq_request=seq_request,
            library_mapping_form=library_mapping_form,
            **context
        )
    )


# 5. Map libraries
@seq_request_form_htmx.route("<int:seq_request_id>/map_libraries", methods=["POST"])
@login_required
def map_libraries(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    library_mapping_form = forms.LibraryMappingForm()
    validated, library_mapping_form = library_mapping_form.custom_validate(db.db_handler)
    context = library_mapping_form.prepare()  # this needs to be after validation

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/step-5.html",
                seq_request=seq_request,
                library_mapping_form=library_mapping_form,
                **context
            )
        )
    
    df = library_mapping_form.parse()
    pool_mapping_form = forms.PoolMappingForm(formdata=None)
    context = pool_mapping_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/seq_request/step-6.html",
            seq_request=seq_request,
            pool_mapping_form=pool_mapping_form,
            **context
        )
    )


# 6. Map pools
@seq_request_form_htmx.route("<int:seq_request_id>/map_pools", methods=["POST"])
@login_required
def map_pools(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    pool_mapping_form = forms.PoolMappingForm()
    validated, pool_mapping_form = pool_mapping_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/step-6.html",
                seq_request=seq_request,
                pool_mapping_form=pool_mapping_form,
                **pool_mapping_form.prepare()
            )
        )
    
    df = pool_mapping_form.parse()
    library_select_form = forms.LibrarySelectForm()
    context = library_select_form.prepare(seq_request.id, df)

    return make_response(
        render_template(
            template_name_or_list="components/popups/seq_request/step-7.html",
            seq_request=seq_request,
            library_select_form=library_select_form,
            **context
        ), push_url=False
    )


# 7. Confirm libraries
@seq_request_form_htmx.route("<int:seq_request_id>/confirm_libraries", methods=["POST"])
@login_required
def confirm_libraries(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    library_select_form = forms.LibrarySelectForm()
    context = library_select_form.prepare(seq_request.id)
    
    validated, library_select_form = library_select_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/step-7.html",
                seq_request=seq_request,
                library_select_form=library_select_form,
                **context
            ), push_url=False
        )

    df = library_select_form.parse()

    barcode_check_form = forms.BarcodeCheckForm()
    context = barcode_check_form.prepare(df)

    return make_response(
        render_template(
            "components/popups/seq_request/step-8.html",
            seq_request=seq_request,
            barcode_check_form=barcode_check_form,
            **context
        )
    )


# 8. Check barcodes
@seq_request_form_htmx.route("<int:seq_request_id>/check_barcodes", methods=["POST"])
@login_required
def check_barcodes(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    barcode_check_form = forms.BarcodeCheckForm()
    validated, barcode_check_form = barcode_check_form.custom_validate()
    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/step-8.html",
                seq_request=seq_request,
                barcode_check_form=barcode_check_form,
                **barcode_check_form.prepare()
            )
        )
    df = barcode_check_form.parse()

    n_added = 0
    n_new_samples = 0
    n_new_projects = 0

    with DBSession(db.db_handler) as session:
        projects: dict[int | str, models.Project] = {}
        for project_id, project_name in df[["project_id", "project_name"]].drop_duplicates().values.tolist():
            if not pd.isnull(project_id):
                project_id = int(project_id)
                if (project := session.get_project(project_id)) is None:
                    raise Exception(f"Project with id {project_id} does not exist.")
                
                projects[project_id] = project
            else:
                project = session.create_project(
                    name=project_name,
                    description="",
                    owner_id=current_user.id
                )
                projects[project.id] = project
                df.loc[df["project_name"] == project_name, "project_id"] = project.id

        if df["project_id"].isna().any():
            raise Exception("Project id is None (should not be).")

    with DBSession(db.db_handler) as session:
        pools: dict[str, models.Pool] = {}
        for pool_label, _df in df.groupby("pool"):
            pool_label = str(pool_label)
            pool = session.create_pool(
                name=pool_label,
                owner_id=current_user.id,
                index_kit_id=df["index_kit"].iloc[0] if not pd.isnull(df["index_kit"].iloc[0]) else None,
                contact_name=_df["contact_person_name"].iloc[0],
                contact_email=_df["contact_person_email"].iloc[0],
                contact_phone=_df["contact_person_phone"].iloc[0],
            )
            pools[pool_label] = pool

        for (_sample_name, _sample_id, _tax_id, _project_name, _project_id), _df in df.groupby(["sample_name", "sample_id", "tax_id", "project_name", "project_id"], dropna=False):
            project = projects[_project_id]
            logger.debug(f"{_sample_name}, {_sample_id}, {_tax_id}, {_project_name}, {_project_id}")
            if pd.isna(_sample_id):
                logger.debug(f"Creating sample '{_sample_name}' in project '{project.name}'.")
                sample = session.create_sample(
                    name=_sample_name,
                    organism_tax_id=int(_tax_id),
                    project_id=project.id,
                    owner_id=current_user.id
                )
                n_new_samples += 1
            else:
                logger.debug(f"Getting sample '{_sample_name}' with id '{_sample_id}'.")
                sample = session.get_sample(int(_sample_id))

            for i, row in _df.iterrows():
                library = session.create_library(
                    sample_id=sample.id,
                    library_type=LibraryType.get(row["library_type_id"]),
                    owner_id=current_user.id,
                    volume=row["library_volume"],
                    dna_concentration=row["library_concentration"],
                    total_size=row["library_total_size"],
                    index_1_sequence=row["index_1"] if not pd.isna(row["index_1"]) else None,
                    index_2_sequence=row["index_2"] if not pd.isna(row["index_2"]) else None,
                    index_3_sequence=row["index_3"] if not pd.isna(row["index_3"]) else None,
                    index_4_sequence=row["index_4"] if not pd.isna(row["index_4"]) else None,
                    index_1_adapter=row["adapter_1"] if not pd.isna(row["adapter_1"]) else None,
                    index_2_adapter=row["adapter_2"] if not pd.isna(row["adapter_2"]) else None,
                    index_3_adapter=row["adapter_3"] if not pd.isna(row["adapter_3"]) else None,
                    index_4_adapter=row["adapter_4"] if not pd.isna(row["adapter_4"]) else None,
                )
                session.link_library_pool(
                    library_id=library.id,
                    pool_id=pools[row["pool"]].id
                )
                
                session.link_library_seq_request(
                    library_id=library.id,
                    seq_request_id=seq_request.id
                )

                n_added += 1

    logger.info(f"Created '{n_new_samples}' samples and '{n_new_projects}' projects.")
    if n_added == 0:
        flash("No samples added.", "warning")
    elif n_added == len(df):
        flash(f"Added all ({n_added}) samples to sequencing request.", "success")
    elif n_added < len(df):
        flash(f"Some samples ({len(df) - n_added}) could not be added.", "warning")

    return make_response(
        redirect=url_for(
            "seq_requests_page.seq_request_page",
            seq_request_id=seq_request.id
        ),
    )