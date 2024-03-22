import os
from typing import TYPE_CHECKING, Literal

import pandas as pd

from flask import Blueprint, request, abort, send_file, current_app, Response
from flask_login import login_required

from limbless_db import models
from limbless_db.categories import HTTPResponse, LibraryType

from .... import db
from ....forms.workflows import library_annotation as forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_annotation_workflow = Blueprint("library_annotation_workflow", __name__, url_prefix="/api/workflows/seq_request_form/")


# Template sample annotation sheet
@library_annotation_workflow.route("download_template/<string:type>", methods=["GET"])
@login_required
def download_template(type: str):
    if type == "raw":
        name = "raw_sample_annotation.tsv"
        df = pd.DataFrame(columns=list(forms.SASInputForm._feature_mapping_raw.keys()))
    elif type == "premade":
        df = pd.DataFrame(columns=list(forms.SASInputForm._feature_mapping_premade.keys()))
        name = "premade_library_annotation.tsv"
    elif type == "cmo":
        df = pd.DataFrame(columns=list(forms.CMOReferenceInputForm._mapping.keys()))
        name = "cmo_reference.tsv"
    elif type == "feature":
        df = pd.DataFrame(columns=list(forms.FeatureKitReferenceInputForm._mapping.keys()))
        name = "feature_reference.tsv"
    else:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={name}"}
    )


# Template sample annotation sheet
@library_annotation_workflow.route("download_visium_template/<string:uuid>", methods=["GET"])
@login_required
def download_visium_template(uuid: str):
    form = forms.VisiumAnnotationForm(uuid=uuid)
    data = form.get_data()
    df = data["library_table"]
    df = df[df["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id][["library_name"]]
    df = df.rename(columns={"library_name": "Library Name"})

    for col in forms.VisiumAnnotationForm._visium_annotation_mapping.keys():
        if col not in df.columns:
            df[col] = ""

    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=visium_annotation.tsv"}
    )


# Template sequencing authorization form
@library_annotation_workflow.route("seq_auth_form/download", methods=["GET"])
@login_required
def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"

    if current_app.static_folder is None:
        return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
    
    path = os.path.join(
        current_app.static_folder, "resources", "templates", name
    )

    return send_file(path, mimetype="pdf", as_attachment=True, download_name=name)


# 0. Restart form
@library_annotation_workflow.route("<int:seq_request_id>/begin/<string:type>", methods=["GET"])
@login_required
def begin(seq_request_id: int, type: Literal["raw", "pooled"]):
    if type not in ["raw", "pooled"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if current_user.id != seq_request.requestor_id and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.SASInputForm(type=type)
    
    return form.make_response(
        seq_request=seq_request, type=type, columns=form.get_columns(), colors=forms.SASInputForm.colors
    )
        

# 1. Input sample annotation sheet
@library_annotation_workflow.route("<int:seq_request_id>/parse_table/<string:type>", methods=["POST"])
@login_required
def parse_table(seq_request_id: int, type: Literal["raw", "pooled"]):
    if type not in ["raw", "pooled"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.SASInputForm(
        type=type,
        formdata=request.form | request.files,
    ).process_request(
        seq_request=seq_request, user_id=current_user.id
    )


# 2. Select project
@library_annotation_workflow.route("<int:seq_request_id>/project_select", methods=["POST"])
@login_required
def select_project(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.ProjectMappingForm(formdata=request.form).process_request(
        seq_request=seq_request, user_id=current_user.id,
        seq_request_id=seq_request_id
    )


# 3. Map organisms if new samples
@library_annotation_workflow.route("<int:seq_request_id>/map_genomes", methods=["POST"])
@login_required
def map_genomes(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.GenomeRefMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 4. Map libraries
@library_annotation_workflow.route("<int:seq_request_id>/map_libraries", methods=["POST"])
@login_required
def map_libraries(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.LibraryMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 5. Map index_kits
@library_annotation_workflow.route("<int:seq_request_id>/map_index_kits", methods=["POST"])
@login_required
def map_index_kits(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.IndexKitMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 6.1. Specify Features
@library_annotation_workflow.route("<int:seq_request_id>/parse_cmo_reference", methods=["POST"])
@login_required
def parse_cmo_reference(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.CMOReferenceInputForm(formdata=request.form | request.files).process_request(
        seq_request=seq_request
    )


# 6.2. Specify Features
@library_annotation_workflow.route("<int:seq_request_id>/parse_feature_reference", methods=["POST"])
@login_required
def parse_feature_reference(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.FeatureKitReferenceInputForm(formdata=request.form | request.files).process_request(
        seq_request=seq_request
    )


# 7. Map Feature Kits
@library_annotation_workflow.route("<int:seq_request_id>/map_feature_kits", methods=["POST"])
@login_required
def map_feature_kits(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    return forms.FeatureKitMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 8. Map pools
@library_annotation_workflow.route("<int:seq_request_id>/annotate_visium", methods=["POST"])
@login_required
def annotate_visium(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.VisiumAnnotationForm(formdata=request.form | request.files).process_request(
        seq_request=seq_request
    )

    
# 9. Map pools
@library_annotation_workflow.route("<int:seq_request_id>/map_pools", methods=["POST"])
@login_required
def map_pools(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.PoolMappingForm(formdata=request.form).process_request(
        seq_request=seq_request
    )


# 10. Check barcodes
@library_annotation_workflow.route("<int:seq_request_id>/check_barcodes", methods=["POST"])
@login_required
def check_barcodes(seq_request_id: int):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return forms.BarcodeCheckForm(formdata=request.form).process_request(
        seq_request=seq_request, user_id=current_user.id
    )
