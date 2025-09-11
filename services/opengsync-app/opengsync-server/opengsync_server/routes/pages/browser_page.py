from pathlib import Path

from flask import Blueprint, render_template

from opengsync_db import models

from ... import db, logger
from ...tools import FileBrowser
from ...core import wrappers, exceptions, runtime

browser_page_bp = Blueprint("browser_page", __name__, url_prefix="/browser")

@wrappers.page_route(browser_page_bp, db=db, login_required=True, cache_timeout_seconds=60)
def files(current_user: models.User, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")

    browser = FileBrowser(runtime.app.share_root, db=db)

    logger.debug(browser.list_contents(subpath))
    
    return render_template(
        "files_page.html", 
        paths=browser.list_contents(subpath),
        current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
    )