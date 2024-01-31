import os
from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, request, abort, send_file, current_app
from flask_htmx import make_response
from flask_login import login_required

import pandas as pd

from .... import db, logger, forms, models
from ....core import DBSession
from ....categories import HttpResponse, LibraryType

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user


seq_request_form_htmx = Blueprint("seq_request_form_htmx", __name__, url_prefix="/api/seq_request_form/")


# Template sample annotation sheet
@seq_request_form_htmx.route("download_template/<string:type>", methods=["GET"])
@login_required
def download_template(type: str):
    if type == "raw":
        name = "sas_raw_libraries.tsv"
    elif type == "premade":
        name = "sas_premade_libraries.tsv"
    elif type == "feature":
        name = "feature.tsv"
    else:
        return abort(HttpResponse.NOT_FOUND.value.id)

    path = os.path.join(
        current_app.root_path, "..",
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
            "components/popups/seq_request/seq_request-1.html",
            table_form=forms.TableForm("seq_request"),
            seq_request=seq_request
        ), push_url=False
    )


# 1. Input sample annotation sheet
@seq_request_form_htmx.route("<int:seq_request_id>/parse_table", methods=["POST"])
@login_required
def parse_table(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    table_input_form = forms.TableForm("seq_request")
    validated, table_input_form = table_input_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-1.html",
                table_form=table_input_form, seq_request=seq_request
            ), push_url=False
        )
    
    try:
        df = table_input_form.parse()
    except pd.errors.ParserError as e:
        table_input_form.file.errors = (str(e),)
            
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-1.html",
                table_form=table_input_form, seq_request=seq_request
            ), push_url=False
        )
    
    data = {"library_table": df}
    table_col_form = forms.SampleColTableForm(None, None)
    context = table_col_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-2.html",
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

    sample_table_form = forms.SampleColTableForm(None, request.form)
    context = sample_table_form.prepare()
    validated, sample_table_form = sample_table_form.custom_validate()
    
    if not validated:
        # TODO: show errors
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-2.html",
                sample_table_form=sample_table_form,
                data=sample_table_form.get_data().values.tolist(),
                seq_request=seq_request,
                **context
            ),
            push_url=False
        )

    data = sample_table_form.parse()
    project_mapping_form = forms.ProjectMappingForm(sample_table_form.uuid, None)
    context = project_mapping_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-3.html",
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
    
    project_mapping_form = forms.ProjectMappingForm(None, request.form)
    validated, project_mapping_form = project_mapping_form.custom_validate(db.db_handler, current_user.id)

    if not validated:
        context = project_mapping_form.prepare()
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-3.html",
                project_mapping_form=project_mapping_form,
                seq_request=seq_request, **context
            ), push_url=False
        )
    
    data = project_mapping_form.parse(seq_request_id=seq_request_id)

    if data["library_table"]["sample_id"].isna().any():
        organism_mapping_form = forms.OrganismMappingForm(project_mapping_form.uuid, None)
        context = organism_mapping_form.prepare(data)
        # new sample -> map organisms
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-4.html",
                organism_mapping_form=organism_mapping_form,
                seq_request=seq_request, **context
            ), push_url=False
        )

    library_mapping_form = forms.LibraryMappingForm(project_mapping_form.uuid, None)
    context = library_mapping_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-5.html",
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
    
    organism_mapping_form = forms.OrganismMappingForm(None, request.form)
    validated, organism_mapping_form = organism_mapping_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-4.html",
                organism_mapping_form=organism_mapping_form,
                seq_request=seq_request,
                **organism_mapping_form.prepare()
            ), push_url=False
        )
    
    data = organism_mapping_form.parse()
    library_mapping_form = forms.LibraryMappingForm(organism_mapping_form.uuid, None)
    context = library_mapping_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-5.html",
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
    
    library_mapping_form = forms.LibraryMappingForm(None, request.form)
    validated, library_mapping_form = library_mapping_form.custom_validate(db.db_handler)
    context = library_mapping_form.prepare()  # this needs to be after validation

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-5.html",
                seq_request=seq_request,
                library_mapping_form=library_mapping_form,
                **context
            )
        )
    
    data = library_mapping_form.parse()

    if "index_kit" in data["library_table"]:
        index_kit_mapping_form = forms.IndexKitMappingForm(library_mapping_form.uuid, None)
        context = index_kit_mapping_form.prepare(data)

        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-6.html",
                seq_request=seq_request,
                index_kit_mapping_form=index_kit_mapping_form,
                **context
            )
        )
    
    if data["library_table"]["library_type_id"].isin([
        LibraryType.ANTIBODY_CAPTURE.value.id,
        LibraryType.MULTIPLEXING_CAPTURE.value.id,
    ]).any():
        feature_input_form = forms.FeatureInputForm(library_mapping_form.uuid, None)
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-7.html",
                seq_request=seq_request,
                feature_input_form=feature_input_form,
                **feature_input_form.prepare()
            )
        )
    
    if "pool" in data["library_table"].columns:
        pool_mapping_form = forms.PoolMappingForm(library_mapping_form.uuid, None)
        context = pool_mapping_form.prepare(data)

        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-9.html",
                seq_request=seq_request,
                pool_mapping_form=pool_mapping_form,
                **context
            )
        )

    library_select_form = forms.LibrarySelectForm(library_mapping_form.uuid, None)
    context = library_select_form.prepare(data)

    return make_response(
        render_template(
            template_name_or_list="components/popups/seq_request/seq_request-10.html",
            seq_request=seq_request,
            library_select_form=library_select_form,
            **context
        ), push_url=False
    )


# 6. Map index_kits
@seq_request_form_htmx.route("<int:seq_request_id>/map_index_kits", methods=["POST"])
@login_required
def map_index_kits(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    index_kit_mapping_form = forms.IndexKitMappingForm(None, request.form)
    validated, index_kit_mapping_form = index_kit_mapping_form.custom_validate()
    
    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-6.html",
                seq_request=seq_request,
                index_kit_mapping_form=index_kit_mapping_form,
                **index_kit_mapping_form.prepare()
            )
        )

    data = index_kit_mapping_form.parse()
    feature_input_form = forms.FeatureInputForm(index_kit_mapping_form.uuid, None)
    context = feature_input_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-7.html",
            seq_request=seq_request,
            feature_input_form=feature_input_form,
            **context
        )
    )


# 7. Specify Features
@seq_request_form_htmx.route("<int:seq_request_id>/parse_feature_form", methods=["POST"])
@login_required
def parse_feature_form(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    feature_input_form = forms.FeatureInputForm(None, request.form)
    validated, feature_input_form = feature_input_form.custom_validate()
    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-7.html",
                seq_request=seq_request,
                feature_input_form=feature_input_form,
                **feature_input_form.prepare()
            )
        )
    
    try:
        data = feature_input_form.parse()
    except pd.errors.ParserError as e:
        feature_input_form.file.errors = (str(e),)
            
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-7.html",
                seq_request=seq_request,
                feature_input_form=feature_input_form,
                **feature_input_form.prepare()
            )
        )
    
    feature_kit_mapping_form = forms.FeatureKitMappingForm(feature_input_form.uuid, None)
    context = feature_kit_mapping_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-8.html",
            seq_request=seq_request,
            feature_kit_mapping_form=feature_kit_mapping_form,
            **context
        )
    )


# 8. Map Feature Kits
@seq_request_form_htmx.route("<int:seq_request_id>/map_feature_kits", methods=["POST"])
@login_required
def map_feature_kits(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    feature_kit_mapping_form = forms.FeatureKitMappingForm(None, request.form)
    validated, feature_kit_mapping_form = feature_kit_mapping_form.custom_validate()
    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-8.html",
                seq_request=seq_request,
                feature_kit_mapping_form=feature_kit_mapping_form,
                **feature_kit_mapping_form.prepare()
            )
        )
    
    data = feature_kit_mapping_form.parse()

    if "pool" in data["library_table"].columns:
        pool_mapping_form = forms.PoolMappingForm(feature_kit_mapping_form.uuid, None)
        context = pool_mapping_form.prepare(data)

        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-9.html",
                seq_request=seq_request,
                pool_mapping_form=pool_mapping_form,
                **context
            )
        )
    
    library_select_form = forms.LibrarySelectForm(feature_kit_mapping_form.uuid, None)
    context = library_select_form.prepare(data)

    return make_response(
        render_template(
            template_name_or_list="components/popups/seq_request/seq_request-10.html",
            seq_request=seq_request,
            library_select_form=library_select_form,
            **context
        ), push_url=False
    )

    
# 9. Map pools
@seq_request_form_htmx.route("<int:seq_request_id>/map_pools", methods=["POST"])
@login_required
def map_pools(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    pool_mapping_form = forms.PoolMappingForm(None, request.form)
    validated, pool_mapping_form = pool_mapping_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-9.html",
                seq_request=seq_request,
                pool_mapping_form=pool_mapping_form,
                **pool_mapping_form.prepare()
            )
        )
    
    data = pool_mapping_form.parse()
    library_select_form = forms.LibrarySelectForm(pool_mapping_form.uuid, None)
    context = library_select_form.prepare(data)

    return make_response(
        render_template(
            template_name_or_list="components/popups/seq_request/seq_request-10.html",
            seq_request=seq_request,
            library_select_form=library_select_form,
            **context
        ), push_url=False
    )


# 10. Confirm libraries
@seq_request_form_htmx.route("<int:seq_request_id>/confirm_libraries", methods=["POST"])
@login_required
def confirm_libraries(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    library_select_form = forms.LibrarySelectForm(None, request.form)
    context = library_select_form.prepare()
    
    validated, library_select_form = library_select_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-10.html",
                seq_request=seq_request,
                library_select_form=library_select_form,
                **context
            ), push_url=False
        )

    data = library_select_form.parse()
    barcode_check_form = forms.BarcodeCheckForm(library_select_form.uuid, None)
    context = barcode_check_form.prepare(data)

    return make_response(
        render_template(
            "components/popups/seq_request/seq_request-11.html",
            seq_request=seq_request,
            barcode_check_form=barcode_check_form,
            **context
        )
    )


# 11. Check barcodes
@seq_request_form_htmx.route("<int:seq_request_id>/check_barcodes", methods=["POST"])
@login_required
def check_barcodes(seq_request_id: int):
    if (seq_request := db.db_handler.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    barcode_check_form = forms.BarcodeCheckForm(None, request.form)
    validated, barcode_check_form = barcode_check_form.custom_validate()
    if not validated:
        return make_response(
            render_template(
                "components/popups/seq_request/seq_request-11.html",
                seq_request=seq_request,
                barcode_check_form=barcode_check_form,
                **barcode_check_form.prepare()
            )
        )
    data = barcode_check_form.parse()

    library_table = data["library_table"]
    feature_table = data["feature_table"] if "feature_table" in data else None

    n_added = 0
    n_new_samples = 0
    n_new_projects = 0

    with DBSession(db.db_handler) as session:
        projects: dict[int | str, models.Project] = {}
        for project_id, project_name in library_table[["project_id", "project_name"]].drop_duplicates().values.tolist():
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
                library_table.loc[library_table["project_name"] == project_name, "project_id"] = project.id

        if library_table["project_id"].isna().any():
            raise Exception("Project id is None (should not be).")

    with DBSession(db.db_handler) as session:
        pools: dict[str, models.Pool] = {}

        if "pool" in library_table.columns:
            for pool_label, _df in library_table.groupby("pool"):
                pool_label = str(pool_label)
                pool = session.create_pool(
                    name=pool_label,
                    owner_id=current_user.id,
                    seq_request_id=seq_request_id,
                    contact_name=_df["contact_person_name"].iloc[0],
                    contact_email=_df["contact_person_email"].iloc[0],
                    contact_phone=_df["contact_person_phone"].iloc[0],
                )
                pools[pool_label] = pool

        for (sample_name, sample_id, tax_id, project_id, is_cmo_sample), _df in library_table.groupby(["sample_name", "sample_id", "tax_id", "project_id", "is_cmo_sample"], dropna=False):
            if feature_table is not None:
                feature_ref = feature_table.loc[feature_table["sample_pool"] == sample_name, :]
            else:
                feature_ref = pd.DataFrame()
            library_samples: list[tuple[models.Sample, Optional[models.CMO]]] = []

            sample_id = int(sample_id) if not pd.isna(sample_id) else None
            project_id = int(project_id)
            tax_id = int(tax_id)

            if is_cmo_sample:
                for _, row in feature_ref.iterrows():
                    feature = session.get_feature(row["feature_id"])
                    sample = session.create_sample(
                        name=row["biosample"],
                        organism_tax_id=tax_id,
                        owner_id=current_user.id,
                        project_id=project_id,
                    )
                    # Temporary data object
                    logger.debug(feature)
                    cmo = models.CMO(
                        sequence=feature.sequence,
                        pattern=feature.pattern,
                        read=feature.read,
                        sample_id=0,
                        library_id=0,
                    )
                    
                    library_samples.append((sample, cmo))
                    n_new_samples += 1
            else:
                
                if sample_id is None:
                    logger.debug(f"Creating sample '{sample_name}' in project '{project_id}'.")
                    sample = session.create_sample(
                        name=sample_name,
                        organism_tax_id=tax_id,
                        project_id=project_id,
                        owner_id=current_user.id
                    )
                    library_samples.append((sample, None))
                    n_new_samples += 1
                else:
                    logger.debug(f"Getting sample '{sample_name}' with id '{sample_id}'.")
                    sample = session.get_sample(sample_id)
                    library_samples.append((sample, None))

            for _, row in _df.iterrows():
                library_type = LibraryType.get(row["library_type_id"])

                index_kit_id = int(row["index_kit_id"]) if "index_kit_id" in row and not pd.isna(row["index_kit_id"]) else None
                library_volume = row["library_volume"] if "library_volume" in row and not pd.isna(row["library_volume"]) else None
                dna_concentration = row["library_concentration"] if "library_concentration" in row and not pd.isna(row["library_concentration"]) else None
                total_size = row["library_total_size"] if "library_total_size" in row and not pd.isna(row["library_total_size"]) else None
                adapter = row["adapter"] if "adapter" in row and not pd.isna(row["adapter"]) else None
                index_1_sequence = row["index_1"] if "index_1" in row and not pd.isna(row["index_1"]) else None
                index_2_sequence = row["index_2"] if "index_2" in row and not pd.isna(row["index_2"]) else None
                index_3_sequence = row["index_3"] if "index_3" in row and not pd.isna(row["index_3"]) else None
                index_4_sequence = row["index_4"] if "index_4" in row and not pd.isna(row["index_4"]) else None

                library = session.create_library(
                    name=sample_name + "_" + library_type.value.description,
                    seq_request_id=seq_request.id,
                    library_type=library_type,
                    index_kit_id=index_kit_id,
                    owner_id=current_user.id,
                    volume=library_volume,
                    dna_concentration=dna_concentration,
                    total_size=total_size,
                    index_1_sequence=index_1_sequence,
                    index_2_sequence=index_2_sequence,
                    index_3_sequence=index_3_sequence,
                    index_4_sequence=index_4_sequence,
                    adapter=adapter,
                )
                n_added += 1
            
                for sample, cmo in library_samples:
                    if cmo is not None:
                        logger.debug(cmo.pattern)
                        _cmo = session.create_cmo(
                            sequence=cmo.sequence,
                            pattern=cmo.pattern,
                            read=cmo.read,
                            sample_id=sample.id,
                            library_id=library.id,
                        )
                        session.link_sample_library(
                            sample_id=sample.id,
                            library_id=library.id,
                            cmo_id=_cmo.id,
                        )
                    else:
                        session.link_sample_library(
                            sample_id=sample.id,
                            library_id=library.id,
                        )

                if "pool" in row and not pd.isna(row["pool"]):
                    library.pool_id = pools[row["pool"]].id
                    library = session.update_library(library)

    logger.debug(f"Created '{n_new_samples}' samples and '{n_new_projects}' projects.")

    if n_added == 0:
        flash("No libraries added.", "warning")
    else:
        flash(f"Added {n_added} libraries to sequencing request.", "success")

    return make_response(
        redirect=url_for(
            "seq_requests_page.seq_request_page",
            seq_request_id=seq_request.id
        ),
    )