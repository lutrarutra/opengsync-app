from typing import Annotated

from flask import Blueprint, Response, jsonify

from opengsync_db import models


from ...core import wrappers, exceptions
from ... import db
from ...tools.routes import JSON, ARGS, FORM


shares_api_bp = Blueprint("shares_api", __name__, url_prefix="/api/shares/")


@wrappers.api_route(shares_api_bp, db=db, methods=["POST"])
def add_share_path_to_project(api_token: JSON[str] = "asdasd", project_id: JSON[int]):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException("Project not found")

    return jsonify({"result": "success", "token": api_token}), 200
