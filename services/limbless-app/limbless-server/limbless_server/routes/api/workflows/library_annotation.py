import os
from typing import TYPE_CHECKING, Literal

from flask import Blueprint, request, abort, send_file, current_app
from flask_login import login_required

from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse, SubmissionType

from .... import db, logger  # noqa
from ....forms.workflows import library_annotation as forms
from ....forms.MultiStepForm import MultiStepForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

library_annotation_workflow = Blueprint("library_annotation_workflow", __name__, url_prefix="/api/workflows/library_annotation/")


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
@library_annotation_workflow.route("<int:seq_request_id>/begin/<string:workflow_type>", methods=["GET"])
@login_required
def begin(seq_request_id: int, workflow_type: Literal["raw", "pooled", "tech"]):
    if workflow_type not in ["raw", "pooled", "tech"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if workflow_type == "pooled":
        if seq_request.submission_type != SubmissionType.POOLED_LIBRARIES:
            return abort(HTTPResponse.BAD_REQUEST.id)
    elif workflow_type == "raw":
        if seq_request.submission_type != SubmissionType.RAW_SAMPLES:
            return abort(HTTPResponse.BAD_REQUEST.id)
    elif workflow_type == "tech":
        if seq_request.submission_type != SubmissionType.RAW_SAMPLES:
            return abort(HTTPResponse.BAD_REQUEST.id)
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    form = forms.ProjectSelectForm(workflow_type=workflow_type, seq_request=seq_request)
    return form.make_response()
        

# 0. Step
@library_annotation_workflow.route("<int:seq_request_id>/previous/<string:uuid>", methods=["GET"])
@login_required
def previous(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if (response := MultiStepForm.pop_last_step("library_annotation", uuid)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    step_name, step = response

    prev_step_cls = forms.steps[step_name]
    prev_step = prev_step_cls(uuid=uuid, seq_request=seq_request, **step.args)
    prev_step.fill_previous_form()
    return prev_step.make_response()


# 1.1 Select project
@library_annotation_workflow.route("<int:seq_request_id>/project_select/<string:workflow_type>", methods=["POST"])
@db_session(db)
@login_required
def select_project(seq_request_id: int, workflow_type: str):
    if workflow_type not in ["tech", "raw", "pooled"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        forms.ProjectSelectForm(seq_request=seq_request, workflow_type=workflow_type)
    
    return forms.ProjectSelectForm(seq_request=seq_request, workflow_type=workflow_type, formdata=request.form).process_request(user=current_user)
    

# 1.2 Pool Definition
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/define_pools", methods=["POST", "GET"])
@db_session(db)
@login_required
def define_pools(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if request.method == "GET":
        return forms.PoolMappingForm(uuid=uuid, seq_request=seq_request).make_response()
    
    return forms.PoolMappingForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request(user=current_user)


# 1.2. Specify Barcodes
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_barcode_table", methods=["POST"])
@login_required
def parse_barcode_table(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    return forms.BarcodeInputForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 1.3 Index Kit Mapping
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/map_index_kits", methods=["POST"])
@login_required
def map_index_kits(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.IndexKitMappingForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_assay_form", methods=["POST"])
@db_session(db)
@login_required
def parse_assay_form(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return forms.SelectAssayForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 2. Input sample annotation sheet
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_table/<string:form_type>", methods=["POST"])
@db_session(db)
@login_required
def parse_table(seq_request_id: int, uuid: str, form_type: Literal["pooled", "raw", "tech", "tech-multiplexed"]):
    if form_type not in ["pooled", "raw", "tech", "tech-multiplexed"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    if form_type == "pooled":
        form = forms.PooledLibraryAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form)
    elif form_type == "raw":
        form = forms.LibraryAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form)
    elif form_type == "tech":
        form = forms.DefineSamplesForm(uuid=uuid, seq_request=seq_request, formdata=request.form)
    elif form_type == "tech-multiplexed":
        form = forms.DefineMultiplexedSamplesForm(uuid=uuid, seq_request=seq_request, formdata=request.form)

    return form.process_request()


# 6. Specify CMO reference
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_cmo_reference", methods=["POST"])
@login_required
def parse_cmo_reference(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.CMOAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 7. Specify Features
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/annotate_features", methods=["POST"])
@login_required
def annotate_features(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    return forms.FeatureAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 8. Map Feature Kits
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/map_feature_kits", methods=["POST"])
@login_required
def map_feature_kits(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    return forms.KitMappingForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 9. Visium Annotation
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_visium_reference", methods=["POST"])
@login_required
def parse_visium_reference(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.VisiumAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 10. Flex Annotation
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_flex_annotation", methods=["POST"])
@login_required
def parse_flex_annotation(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.FlexAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


# 11. Parse sample annotations
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/parse_sas_form", methods=["POST"])
@login_required
def parse_sas_form(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return forms.SampleAttributeAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

    
# Complete SAS
@library_annotation_workflow.route("<int:seq_request_id>/<string:uuid>/complete", methods=["POST"])
@login_required
def complete(seq_request_id: int, uuid: str):
    if (seq_request := db.get_seq_request(seq_request_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
        affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.CompleteSASForm(uuid=uuid, formdata=request.form, seq_request=seq_request)
    return form.process_request(user=current_user)
