from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required


from limbless_db import models, db_session
from limbless_db.categories import HTTPResponse, UserRole
from .... import db, logger, forms

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

plates_htmx = Blueprint("plates_htmx", __name__, url_prefix="/api/hmtx/plates/")


@plates_htmx.route("<int:plate_id>/plate_tab", methods=["GET"])
@db_session(db)
@login_required
def plate_tab(plate_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (plate := db.get_plate(plate_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return make_response(
        render_template(
            "components/plate_tab.html", plate=plate,
        )
    )
