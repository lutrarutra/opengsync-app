from flask import Blueprint, render_template, request
from flask_htmx import make_response

from opengsync_db import models

from ... import db, forms, logger
from ...core import wrappers, exceptions, runtime

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/htmx/auth/")
design_htmx = Blueprint("design_htmx", __name__, url_prefix="/htmx/design/")

@wrappers.htmx_route(design_htmx, db=db)
def flow_cells(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    designs = db.session.query(models.FlowCellDesign).order_by(models.FlowCellDesign.id.desc()).all()

    return make_response(render_template(
        "components/design/flow_cell_design_list.html", designs=designs,
    ))

@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"])
def create_flow_cell_design(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    form = forms.models.FlowCellDesignForm(flow_cell_design=None, formdata=request.form)
    if request.method == "POST":
        return form.process_request()
    
    return form.make_response()

@wrappers.htmx_route(design_htmx, db=db, methods=["GET", "POST"])
def create_pool_design(current_user: models.User, flow_cell_design_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (flow_cell_design := db.session.get(models.FlowCellDesign, flow_cell_design_id)) is None:
        raise exceptions.NotFoundException("Flow Cell Design not found")
    
    form = forms.models.PoolDesignForm(flow_cell_design=flow_cell_design, pool_design=None, formdata=request.form)
    if request.method == "POST":
        return form.process_request()
    
    return form.make_response()
    

