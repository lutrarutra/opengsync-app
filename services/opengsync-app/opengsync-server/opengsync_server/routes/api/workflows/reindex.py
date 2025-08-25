
from flask import Blueprint, request, Response

from opengsync_db import models
from opengsync_db.categories import AccessType

from .... import db, logger
from ....core import wrappers, exceptions
from ....forms.workflows import reindex as forms
from ....forms import SelectSamplesForm
from ....tools import utils
from ....forms.MultiStepForm import MultiStepForm

reindex_workflow = Blueprint("reindex_workflow", __name__, url_prefix="/api/workflows/reindex/")


def get_context(current_user: models.User, args: dict) -> dict:
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        seq_request_id = int(seq_request_id)
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        if db.seq_requests.get_access_type(seq_request, current_user) < AccessType.EDIT:
            raise exceptions.NoPermissionsException()
        context["seq_request"] = seq_request
        
    elif (lab_prep_id := args.get("lab_prep_id")) is not None:
        lab_prep_id = int(lab_prep_id)
        if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        context["lab_prep"] = lab_prep

    elif (pool_id := args.get("pool_id")) is not None:
        pool_id = int(pool_id)
        if (pool := db.pools.get(pool_id)) is None:
            raise exceptions.NotFoundException()
        context["pool"] = pool

    if not current_user.is_insider():
        if "seq_request" not in context:
            raise exceptions.NoPermissionsException()
        
    return context


@wrappers.htmx_route(reindex_workflow, db=db)
def previous(current_user: models.User, uuid: str):
    context = get_context(current_user, request.args)
    
    if (response := MultiStepForm.pop_last_step("reindex", uuid)) is None:
        logger.error("Failed to pop last step")
        raise exceptions.NotFoundException()
    
    step_name, step = response

    if step_name == "select_samples":
        form = SelectSamplesForm(
            "reindex", context=context,
            select_libraries=True
        )
        return form.make_response()

    prev_step_cls = forms.steps[step_name]
    logger.debug(context)
    prev_step = prev_step_cls(
        uuid=uuid,
        seq_request=context.get("seq_request"),  # type: ignore
        lab_prep=context.get("lab_prep"),  # type: ignore
        pool=context.get("pool"),  # type: ignore
        formdata=None
    )  # type: ignore
    prev_step.fill_previous_form(step)
    return prev_step.make_response()


@wrappers.htmx_route(reindex_workflow, db=db)
def begin(current_user: models.User) -> Response:
    context = get_context(current_user, request.args)
        
    form = SelectSamplesForm(
        "reindex", context=context,
        select_libraries=True
    )
    return form.make_response()


@wrappers.htmx_route(reindex_workflow, db=db, methods=["POST"])
def select(current_user: models.User):
    context = get_context(current_user, request.args)

    form: SelectSamplesForm = SelectSamplesForm(
        "reindex", formdata=request.form, context=context,
        select_libraries=True
    )

    if not form.validate():
        return form.make_response()

    libraries = form.get_libraries()
    library_table = utils.get_barcode_table(db, libraries)
    form.add_table("library_table", library_table)
    logger.debug(library_table)
    form.update_data()

    next_form = forms.BarcodeInputForm(
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool"),
        uuid=form.uuid,
        formdata=None
    )
    return next_form.make_response()


@wrappers.htmx_route(reindex_workflow, db=db, methods=["POST"])
def upload_barcode_form(current_user: models.User, uuid: str):
    context = get_context(current_user, request.args)
    
    form = forms.BarcodeInputForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool")
    )
    return form.process_request()


@wrappers.htmx_route(reindex_workflow, db=db, methods=["POST"])
def upload_tenx_atac_barcode_form(current_user: models.User, uuid: str):
    context = get_context(current_user, request.args)
    
    form = forms.TENXATACBarcodeInputForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool")
    )
    return form.process_request()


@wrappers.htmx_route(reindex_workflow, db=db, methods=["POST"])
def map_index_kits(current_user: models.User, uuid: str):
    context = get_context(current_user, request.args)   
    
    form = forms.IndexKitMappingForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool"),
    )
    return form.process_request()


@wrappers.htmx_route(reindex_workflow, db=db, methods=["POST"])
def barcode_match(current_user: models.User, uuid: str):
    context = get_context(current_user, request.args)
    
    return forms.BarcodeMatchForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool")
    ).process_request()


@wrappers.htmx_route(reindex_workflow, db=db, methods=["POST"])
def complete_reindex(current_user: models.User, uuid: str):
    context = get_context(current_user, request.args)
    
    return forms.CompleteReindexForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        pool=context.get("pool")
    ).process_request()
    

    
    