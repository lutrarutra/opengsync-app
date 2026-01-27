import os

from flask import Blueprint, request, send_file

from opengsync_db import models
from opengsync_db.categories import AccessType

from ... import db, logger
from ...forms.workflows import library_annotation as forms
from ...forms.MultiStepForm import MultiStepForm
from ...core import wrappers, exceptions
from ...core.RunTime import runtime

library_annotation_workflow = Blueprint("library_annotation_workflow", __name__, url_prefix="/workflows/library_annotation/")


@wrappers.htmx_route(library_annotation_workflow, db=db)
def download_seq_auth_form():
    name = "seq_auth_form_v2.pdf"

    if runtime.app.static_folder is None:
        raise exceptions.InternalServerErrorException()
    
    path = os.path.join(
        runtime.app.static_folder, "resources", "templates", name
    )

    return send_file(path, mimetype="pdf", as_attachment=True, download_name=name)


@wrappers.htmx_route(library_annotation_workflow, db=db)
def begin(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()

    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    form = forms.ProjectSelectForm(seq_request=seq_request)
    return form.make_response()
        

@wrappers.htmx_route(library_annotation_workflow, db=db)
def previous(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if (response := MultiStepForm.pop_last_step("library_annotation", uuid)) is None:
        logger.error("Failed to pop last step")
        raise exceptions.NotFoundException()
    
    step_name, step = response

    prev_step_cls = forms.steps[step_name]
    prev_step = prev_step_cls(uuid=uuid, seq_request=seq_request, **step.args)  # type: ignore
    prev_step.fill_previous_form(step)
    return prev_step.make_response()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def select_project(current_user: models.User, seq_request_id: int):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        forms.ProjectSelectForm(seq_request=seq_request)
    
    return forms.ProjectSelectForm(seq_request=seq_request, formdata=request.form).process_request(user=current_user)

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_sample_annotation_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
        
    return forms.SampleAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_assay_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
        
    return forms.SelectServiceForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_pooled_library_annotation_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.PooledLibraryAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_custom_assay_annotation_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.CustomAssayAnnotationFrom(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_mux_definition_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.DefineMultiplexedSamplesForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_parse_mux_annotation(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.ParseMuxAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()
    

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST", "GET"])
def define_pools(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.PoolMappingForm(uuid=uuid, seq_request=seq_request).make_response()
    
    return forms.PoolMappingForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request(user=current_user)


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def upload_barcode_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    return forms.BarcodeInputForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def upload_tenx_atac_barcode_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    return forms.TENXATACBarcodeInputForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def barcode_match(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    return forms.BarcodeMatchForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_ocm_reference(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.OCMAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_oligo_mux_reference(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.OligoMuxAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_feature_annotation(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    return forms.FeatureAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_visium_reference(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.VisiumAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_openst_annotation(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.OpenSTAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_flex_annotation(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.FlexAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()

@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_parse_crispr_guide_annotation(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.ParseCRISPRGuideAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def parse_sas_form(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    return forms.SampleAttributeAnnotationForm(uuid=uuid, seq_request=seq_request, formdata=request.form).process_request()


@wrappers.htmx_route(library_annotation_workflow, db=db, methods=["POST"])
def complete(current_user: models.User, seq_request_id: int, uuid: str):
    if (seq_request := db.seq_requests.get(seq_request_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    
    form = forms.CompleteSASForm(uuid=uuid, formdata=request.form, seq_request=seq_request)
    return form.process_request(user=current_user)
