from typing import TYPE_CHECKING

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse, PoolStatus, PoolType

from .... import db, logger, htmx_route  # noqa
from ....forms import SelectSamplesForm
from ....forms.workflows.MergePoolsForm import MergePoolsForm
from ....tools import exceptions

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user  # noqa

merge_pools_workflow = Blueprint("merge_pools_workflow", __name__, url_prefix="/api/workflows/merge_pools/")


def get_context(args: dict) -> dict:
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        seq_request_id = int(seq_request_id)
        if (seq_request := db.get_seq_request(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
            affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
            if affiliation is None:
                raise exceptions.NoPermissionsException()
        context["seq_request"] = seq_request
        
    elif (lab_prep_id := args.get("lab_prep_id")) is not None:
        lab_prep_id = int(lab_prep_id)
        if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        context["lab_prep"] = lab_prep

    if not current_user.is_insider():
        if "seq_request" not in context:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return context


@htmx_route(merge_pools_workflow, db=db)
def begin() -> Response:
    try:
        context = get_context(request.args)
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


@htmx_route(merge_pools_workflow, db=db, methods=["POST"])
def select() -> Response:
    try:
        context = get_context(request.args)
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


@htmx_route(merge_pools_workflow, db=db, methods=["POST"])
def merge(uuid: str) -> Response:
    form = MergePoolsForm(formdata=request.form, uuid=uuid)
    return form.process_request(current_user)