from flask import Blueprint, request

from opengsync_db import models
from opengsync_db.categories import AccessType

from .... import db, logger  # noqa
from ....core import wrappers, exceptions

share_project_data_workflow = Blueprint("share_project_data_workflow", __name__, url_prefix="/api/workflows/dilute_pools/")


@wrappers.htmx_route(share_project_data_workflow, db=db, methods=["GET", "POST"])
def share_project_data(current_user: models.User, project_id: int):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.projects.get_access_type(project, current_user)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()

    from ....forms.workflows.share.ShareProjectDataForm import ShareProjectDataForm

    if request.method == "GET":
        form = ShareProjectDataForm(project)
        return form.make_response()
    elif request.method == "POST":
        return ShareProjectDataForm(project=project, formdata=request.form).process_request(current_user=current_user)
    
    raise exceptions.MethodNotAllowedException()