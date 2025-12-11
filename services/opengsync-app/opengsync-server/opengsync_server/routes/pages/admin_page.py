from flask import Blueprint, render_template, url_for, request

from opengsync_db import models
from opengsync_db.categories import AccessType

from ... import db, logger
from ...core import wrappers, exceptions

admin_pages_bp = Blueprint("admin_pages", __name__)


@wrappers.page_route(admin_pages_bp, db=db, cache_timeout_seconds=360)
def admin_page(current_user: models.User):
    if not current_user.is_admin:
        raise exceptions.NoPermissionsException()
    return render_template("admin_page.html")
