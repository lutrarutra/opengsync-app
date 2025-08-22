from flask import Blueprint, request, abort, Response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse, PoolStatus, PoolType, AccessType

from .... import db
from ....core import wrappers
from ....forms import SelectSamplesForm
from ....forms.workflows.MergePoolsForm import MergePoolsForm
from ....core import exceptions


merge_pools_workflow = Blueprint("merge_pools_workflow", __name__, url_prefix="/api/workflows/merge_pools/")


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

    if not current_user.is_insider():
        if "seq_request" not in context:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return context


@wrappers.htmx_route(merge_pools_workflow, db=db)
def begin(current_user: models.User) -> Response:
    try:
        context = get_context(current_user, request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpeNGSyncServerException as e:
        return abort(e.response.id)
        
    form = SelectSamplesForm(
        "merge_pools",
        context=context,
        select_pools=True,
        pool_status_filter=[
            PoolStatus.DRAFT,
            PoolStatus.SUBMITTED,
            PoolStatus.ACCEPTED,
            PoolStatus.STORED,
        ]
    )
    return form.make_response()


@wrappers.htmx_route(merge_pools_workflow, db=db, methods=["POST"])
def select(current_user: models.User) -> Response:
    try:
        context = get_context(current_user, request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpeNGSyncServerException as e:
        return abort(e.response.id)

    form: SelectSamplesForm = SelectSamplesForm(
        "merge_pools", formdata=request.form, context=context,
        select_pools=True,
        pool_status_filter=[
            PoolStatus.DRAFT,
            PoolStatus.SUBMITTED,
            PoolStatus.ACCEPTED,
            PoolStatus.STORED,
        ]
    )

    # TODO: Check if the user has permission to merge pools
    if not form.validate():
        return form.make_response()

    form.add_table("pool_table", form.pool_table)
    form.metadata = form.metadata | context
    form.update_data()
    
    next_form = MergePoolsForm(uuid=form.uuid, formdata=request.form)
    next_form.contact.selected.data = current_user.id
    next_form.contact.search_bar.data = current_user.name

    if current_user.is_insider():
        next_form.pool_type.data = PoolType.INTERNAL.id
    else:
        next_form.pool_type.data = PoolType.EXTERNAL.id

    return next_form.make_response()


@wrappers.htmx_route(merge_pools_workflow, db=db, methods=["POST"])
def merge(current_user: models.User, uuid: str) -> Response:
    form = MergePoolsForm(formdata=request.form, uuid=uuid)
    return form.process_request(current_user)