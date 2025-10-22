from typing import Annotated

from flask import Blueprint, Response, jsonify

from opengsync_db import models


from ...core import wrappers, exceptions
from ... import db


shares_api_bp = Blueprint("shares_api", __name__, url_prefix="/api/shares/")


@wrappers.api_route(shares_api_bp, db=db, methods=["POST"], json_params=["api_token", "project_id", "path"])
def add_share_path_to_project(api_token: str, project_id: int, path: str):
    return jsonify({"result": "success", "token": api_token, "path": path}), 200
