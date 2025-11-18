from pathlib import Path
import mimetypes

from sqlalchemy import orm
from flask import Blueprint, render_template, Response, send_from_directory, request

from opengsync_db import models

from ... import db, DEBUG, limiter
from ...core import wrappers, exceptions
from ...tools import SharedFileBrowser
from ...core.RunTime import runtime

webdav_bp = Blueprint("webdav", __name__, url_prefix="/files/webdav/")


@wrappers.api_route(webdav_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=300, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="200/minute;5000/hour", methods=["GET", "PROPFIND", "OPTIONS", "HEAD"], api_token_required=False)
def share(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Invalid Token")

    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")

    if limiter.current_limit:
        limiter.storage.clear(limiter.current_limit.key)

    SHARE_ROOT = runtime.app.share_root
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, db=db, share_token=share_token)

    if request.method == "OPTIONS":
        response = Response()
        response.headers["Allow"] = "OPTIONS, GET, PROPFIND"
        response.headers["DAV"] = "1, 2"
        response.headers["Accept-Ranges"] = "bytes"
        return response
    elif request.method == "HEAD":
        if (path := browser.get_file(subpath)) is None:
            raise exceptions.NotFoundException("File not found")
        if not path.is_file():
            raise exceptions.MethodNotAllowedException("Cannot HEAD a collection")

        stat = path.stat()
        response = Response()
        mimetype, _ = mimetypes.guess_type(path.name)
        response.headers["Content-Type"] = mimetype or "application/octet-stream"
        response.headers["Content-Length"] = str(stat.st_size)
        response.headers["Last-Modified"] = browser._format_date(stat.st_mtime)
        return response
    elif request.method == "PROPFIND":
        depth = request.headers.get("Depth", "1")
        if depth not in ("0", "1", "infinity"):
            raise exceptions.BadRequestException("Invalid Depth header")

        depth = 0 if depth == "0" else 1
        resources = browser.propfind(subpath, depth=depth)
        xml = render_template("share/webdav.xml", resources=resources)
        response = Response(xml, status=207)
        response.headers["Content-Type"] = "application/xml; charset=utf-8"
        return response
    elif request.method == "GET":
        if (path := browser.get_file(subpath)) is None:
            raise exceptions.NotFoundException("File not found")

        if not path.is_file():
            raise exceptions.BadRequestException("Subpath must be a file")

        mimetype, _ = mimetypes.guess_type(path.name)
        if not mimetype:
            mimetype = "application/octet-stream"

        if DEBUG:
            return send_from_directory(path.parent, path.name, as_attachment=True, mimetype=mimetype)

        stat = path.stat()
        response = Response()
        response.headers["Content-Type"] = mimetype
        response.headers["X-Accel-Redirect"] = path.as_posix().replace(SHARE_ROOT.as_posix(), "/nginx-share/")
        response.headers["Content-Length"] = str(stat.st_size)
        response.headers["Last-Modified"] = browser._format_date(stat.st_mtime)
        return response
    else:
        raise exceptions.MethodNotAllowedException()
