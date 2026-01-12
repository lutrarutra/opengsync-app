from pathlib import Path

from flask import Blueprint, render_template, request

from opengsync_db import models

from ... import db, logger
from ...core import wrappers, exceptions

browser_page_bp = Blueprint("browser_page", __name__, url_prefix="/browser")

@wrappers.page_route(browser_page_bp, db=db, login_required=True, cache_timeout_seconds=60)
def files(current_user: models.User, subpath: Path = Path()):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if isinstance(subpath, str):
        subpath = Path(subpath)

    sort_by = request.args.get("sort_by", "name")
    sort_order = request.args.get("sort_order", "asc" if sort_by == "name" else "desc")
    
    return render_template(
        "files_page.html", 
        current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        sort_by=sort_by, sort_order=sort_order,
    )





