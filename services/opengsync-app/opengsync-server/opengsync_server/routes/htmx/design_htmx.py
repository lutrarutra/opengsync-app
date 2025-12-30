from pathlib import Path
from flask import Blueprint, url_for, flash, request, render_template
from flask_htmx import make_response
from flask_login import logout_user

from opengsync_db import models
from opengsync_db.categories import UserRole

from ... import db, forms, logger, mail_handler, serializer
from ...core import wrappers, exceptions, runtime, tokens

auth_htmx = Blueprint("auth_htmx", __name__, url_prefix="/htmx/auth/")
design_htmx = Blueprint("design_htmx", __name__, url_prefix="/htmx/design/")

@wrappers.htmx_route(design_htmx, db=db)
def flow_cells(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    designs = [
        models.FlowCellDesign(id=i+1, name=f"Flow Cell Design {i+1}", cycles_r1=150, cycles_r2=150, workflow_id=1)
        for i in range(5)
    ]
    return render_template("components/design/flow_cell_design_list.html", designs=designs)