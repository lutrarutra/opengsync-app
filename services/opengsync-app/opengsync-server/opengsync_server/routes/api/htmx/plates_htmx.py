from flask import Blueprint, render_template
from flask_htmx import make_response


from opengsync_db import models
from .... import db
from ....core import wrappers, exceptions

plates_htmx = Blueprint("plates_htmx", __name__, url_prefix="/api/hmtx/plates/")


@wrappers.htmx_route(plates_htmx, db=db)
def plate_tab(current_user: models.User, plate_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (plate := db.plates.get(plate_id)) is None:
        raise exceptions.NotFoundException()
    
    return make_response(render_template("components/plate.html", plate=plate))