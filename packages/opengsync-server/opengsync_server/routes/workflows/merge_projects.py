from flask import Blueprint, request, Response

from opengsync_db import models

from ... import db
from ...core import wrappers, exceptions
from ...forms.workflows import MergeProjectsForm

merge_projects_workflow = Blueprint("merge_projects_workflow", __name__, url_prefix="/workflows/merge_projects/")


@wrappers.htmx_route(merge_projects_workflow, db=db)
def begin(current_user: models.User) -> Response:
    if not current_user.is_insider:
        raise exceptions.NoPermissionsException()
    
    form = MergeProjectsForm()
    return form.make_response()

@wrappers.htmx_route(merge_projects_workflow, db=db, methods=["POST"])
def complete(current_user: models.User) -> Response:
    if not current_user.is_insider:
        raise exceptions.NoPermissionsException()
    
    form = MergeProjectsForm(formdata=request.form)    
    return form.process_request(current_user)