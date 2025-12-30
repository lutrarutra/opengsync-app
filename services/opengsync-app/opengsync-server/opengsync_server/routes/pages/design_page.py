from flask import Blueprint, render_template

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions

design_page_bp = Blueprint("design_page", __name__)

@wrappers.page_route(design_page_bp, db=db, cache_timeout_seconds=60)
def design(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    return render_template("design_page.html")

