from pathlib import Path
import mimetypes

from sqlalchemy import orm

from flask import Blueprint, render_template, Response, send_from_directory

from opengsync_db import models

from .... import db, DEBUG, limiter
from ....core import wrappers, exceptions
from ....tools import utils, SharedFileBrowser
from ....core.RunTime import runtime

file_share_bp = Blueprint("file_share", __name__, url_prefix="/api/files/")


@wrappers.api_route(file_share_bp, db=db, login_required=False)
def validate(token: str):
    if (share_token := db.shares.get(token)) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
        
    return "OK", 200


@wrappers.api_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60 if not DEBUG else None, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20 per minute")
def rclone(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    if limiter.current_limit:
        limiter.storage.clear(limiter.current_limit.key)

    SHARE_ROOT = runtime.app.share_root

    browser = SharedFileBrowser(
        root_dir=SHARE_ROOT,
        db=db,
        share_token=share_token,
    )

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            mimetype = mimetypes.guess_type(file)[0] or "application/octet-stream"

            if DEBUG:
                return send_from_directory(file.parent, file.name, as_attachment=True, mimetype=mimetype)
            
            response = Response()
            response.headers["Content-Type"] = mimetype
            response.headers["X-Accel-Redirect"] = file.as_posix().replace(SHARE_ROOT.as_posix(), "/nginx-share/")
            return response
        raise exceptions.NotFoundException("File or directory not found")

    return render_template(
        "share/rclone.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )


@wrappers.resource_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60 if not DEBUG else None, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20 per minute")
def browse(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    if limiter.current_limit:
        limiter.storage.clear(limiter.current_limit.key)

    SHARE_ROOT = runtime.app.share_root

    browser = SharedFileBrowser(
        root_dir=SHARE_ROOT,
        db=db,
        share_token=share_token,
    )

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            mimetype = mimetypes.guess_type(file)[0] or "application/octet-stream"

            if DEBUG:
                return send_from_directory(file.parent, file.name, as_attachment=not utils.is_browser_friendly(mimetype), mimetype=mimetype)
            
            response = Response()
            response.headers["Content-Type"] = mimetype
            if not utils.is_browser_friendly(mimetype):
                response.headers["Content-Disposition"] = f"attachment; filename={file.name}"
            response.headers["X-Accel-Redirect"] = file.as_posix().replace(SHARE_ROOT.as_posix(), "/nginx-share/")
            return response
        raise exceptions.NotFoundException("File or directory not found")
        
    paths = sorted(paths, key=lambda p: p.name.lower())

    return render_template(
        "share/browse.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )