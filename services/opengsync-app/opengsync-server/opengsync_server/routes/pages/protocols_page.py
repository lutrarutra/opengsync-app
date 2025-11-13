from flask import Blueprint, render_template, url_for, make_response, request

from opengsync_db import models

from ... import db
from ...core import wrappers, exceptions
protocols_page_bp = Blueprint("protocols_page", __name__)


@wrappers.page_route(protocols_page_bp, db=db, cache_timeout_seconds=360)
def protocols(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
        
    return render_template("protocols_page.html")


@wrappers.page_route(protocols_page_bp, "protocols", db=db, cache_timeout_seconds=360)
def protocol(current_user: models.User, protocol_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (protocol := db.protocols.get(protocol_id)) is None:
        raise exceptions.NotFoundException()

    path_list = [
        ("protocols", url_for("protocols_page.protocols")),
        (f"Protocol {protocol_id}", ""),
    ]

    return render_template(
        "protocol_page.html", path_list=path_list, protocol=protocol,
    )
