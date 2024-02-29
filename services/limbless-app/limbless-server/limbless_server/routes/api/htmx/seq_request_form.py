import os
from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, request, abort, send_file, current_app, Response
from flask_login import login_required

from limbless_db import models
from limbless_db.core.categories import HttpResponse, LibraryType
from .... import db
from ....forms import sas as sas_forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

seq_request_form_htmx = Blueprint("seq_request_form_htmx", __name__, url_prefix="/api/seq_request_form/")


# Template sample annotation sheet
@seq_request_form_htmx.route("download_template/<string:type>", methods=["GET"])
@login_required
def download_template(type: str):
    if type == "raw":
        name = "raw_sample_annotation.tsv"
        df = pd.DataFrame(columns=list(sas_forms.SASInputForm._feature_mapping_raw.keys()))
    elif type == "premade":
        df = pd.DataFrame(columns=list(sas_forms.SASInputForm._feature_mapping_premade.keys()))
        name = "premade_library_annotation.tsv"
    elif type == "cmo":
        df = pd.DataFrame(columns=list(sas_forms.CMOReferenceInputForm._mapping.keys()))
        name = "cmo_reference.tsv"
    elif type == "feature":
        df = pd.DataFrame(columns=list(sas_forms.FeatureKitReferenceInputForm._mapping.keys()))
        name = "feature_reference.tsv"
    else:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={name}"}
    )


# Template sample annotation sheet
@seq_request_form_htmx.route("download_visium_template/<string:uuid>", methods=["GET"])
@login_required
def download_visium_template(uuid: str):
    form = sas_forms.VisiumAnnotationForm(uuid=uuid)
    data = form.get_data()
    df = data["library_table"]
    df = df[df["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id][["library_name"]]
    df = df.rename(columns={"library_name": "Library Name"})

    for col in sas_forms.VisiumAnnotationForm._visium_annotation_mapping.keys():
        if col not in df.columns:
            df[col] = ""

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=visium_annotation.tsv"}
    )


# Template sequencing authorization form
@seq_request_form_htmx.route("seq_auth_form/download", methods=["GET"])
@login_required
def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"

    if current_app.static_folder is None:
        return abort(HttpResponse.INTERNAL_SERVER_ERROR.id)
    
    path = os.path.join(
        current_app.static_folder, "resources", "templates", name
    )

    return send_file(path, mimetype="pdf", as_attachment=True, download_name=name)


# 0. Restart form
@seq_request_form_htmx.route("<int:seq_request_id>/restart_form", methods=["GET"])
@login_required
def restart_form(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.SASInputForm().make_response(
        seq_request=seq_request
    )


# 1. Input sample annotation sheet
@seq_request_form_htmx.route("<int:seq_request_id>/parse_table", methods=["POST"])
@login_required
def parse_table(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.SASInputForm(
        formdata=request.form | request.files
    ).process_request(
        seq_request=seq_request, user_id=current_user.id
    )


# 2. Select project
@seq_request_form_htmx.route("<int:seq_request_id>/project_select", methods=["POST"])
@login_required
def select_project(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.ProjectMappingForm(formdata=request.form).process_request(
        seq_request=seq_request, user_id=current_user.id,
        seq_request_id=seq_request_id
    )


# 3. Map organisms if new samples
@seq_request_form_htmx.route("<int:seq_request_id>/map_organisms", methods=["POST"])
@login_required
def map_organisms(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.OrganismMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 4. Map libraries
@seq_request_form_htmx.route("<int:seq_request_id>/map_libraries", methods=["POST"])
@login_required
def map_libraries(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.LibraryMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 5. Map index_kits
@seq_request_form_htmx.route("<int:seq_request_id>/map_index_kits", methods=["POST"])
@login_required
def map_index_kits(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)

    return sas_forms.IndexKitMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 6.1. Specify Features
@seq_request_form_htmx.route("<int:seq_request_id>/parse_cmo_reference", methods=["POST"])
@login_required
def parse_cmo_reference(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)

    return sas_forms.CMOReferenceInputForm(formdata=request.form | request.files).process_request(
        seq_request=seq_request
    )


# 6.2. Specify Features
@seq_request_form_htmx.route("<int:seq_request_id>/parse_feature_reference", methods=["POST"])
@login_required
def parse_feature_reference(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)

    return sas_forms.FeatureKitReferenceInputForm(formdata=request.form | request.files).process_request(
        seq_request=seq_request
    )


# 7. Map Feature Kits
@seq_request_form_htmx.route("<int:seq_request_id>/map_feature_kits", methods=["POST"])
@login_required
def map_feature_kits(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)

    return sas_forms.FeatureKitMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 8. Map pools
@seq_request_form_htmx.route("<int:seq_request_id>/annotate_visium", methods=["POST"])
@login_required
def annotate_visium(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.VisiumAnnotationForm(formdata=request.form | request.files).process_request(
        seq_request=seq_request
    )

    
# 9. Map pools
@seq_request_form_htmx.route("<int:seq_request_id>/map_pools", methods=["POST"])
@login_required
def map_pools(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.PoolMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 10. Check barcodes
@seq_request_form_htmx.route("<int:seq_request_id>/check_barcodes", methods=["POST"])
@login_required
def check_barcodes(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HttpResponse.NOT_FOUND.id)
    
    return sas_forms.BarcodeCheckForm(formdata=request.form).process_request(
        seq_request=seq_request, user_id=current_user.id
    )
