

from flask import Blueprint, Response

from opengsync_db import models


from ...core import wrappers, exceptions
from ... import db


shares_api_bp = Blueprint("shares_api", __name__, url_prefix="/api/shares/")


@wrappers.api_route(shares_api_bp, db=db)
def add_share_path_to_project(api_token: str, project_id: int, path: str) -> Response:
    return Response()
