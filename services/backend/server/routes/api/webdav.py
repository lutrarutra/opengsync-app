from pathlib import Path
import mimetypes

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, exceptions as exc, config, responses, templates
from ...utils.shared_file_browser import SharedFileBrowser

router = APIRouter(prefix="/webdav", tags=["api", "webdav"], redirect_slashes=False)

WEBDAV_METHODS = ["GET", "PROPFIND", "OPTIONS", "HEAD", "LOCK", "UNLOCK"]


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


@router.api_route("/{token}", methods=WEBDAV_METHODS, name="webdav.share", operation_id="webdav_share")
@router.api_route("/{token}/{subpath:path}", methods=WEBDAV_METHODS, name="webdav.share", operation_id="webdav_share_path")
def share(
    request: Request,
    token: str,
    subpath: str = "",
    session: SyncSession = Depends(dependencies.db_session),
):
    current_path = _subpath(subpath)

    if SharedFileBrowser.OS_JUNK_REGEX.search(current_path.as_posix()):
        return Response(status_code=404)

    if (share_token := session.first(Q.share_token.select(uuid=token).options(orm.selectinload(models.ShareToken.paths)))) is None:
        raise exc.NotFoundException("Invalid Token")

    if share_token.is_expired:
        raise exc.NoPermissionsException("Token expired")

    SHARE_ROOT = Path(config.settings.app_config.share_root)
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, share_token=share_token)

    if request.method == "OPTIONS":
        response = Response()
        response.headers["Allow"] = "OPTIONS, GET, HEAD, PROPFIND"
        response.headers["DAV"] = "1, 2"
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["MS-Author-Via"] = "DAV"
        return response
    elif request.method == "HEAD":
        if (path := browser.get_file(current_path)) is None:
            raise exc.NotFoundException(f"File not found: {current_path}")
        if not path.is_file():
            raise exc.MethodNotAllowedException("Cannot HEAD a collection")

        stat = path.stat()
        mimetype, _ = mimetypes.guess_type(path.name)
        return responses.file_response(
            path,
            filename=path.name,
            content_type=mimetype or "application/octet-stream",
            disposition=None,
            extra_headers={
                "Content-Length": str(stat.st_size),
                "Last-Modified": browser._format_date(stat.st_mtime),
                "ETag": f'"{stat.st_ino}-{stat.st_mtime}-{stat.st_size}"',
            },
            send_body=False,
        )
    if request.method in ["LOCK", "UNLOCK"]:
        # We don't actually support locking (read-only),
        # but returning 204 No Content prevents Windows from showing an error.
        return Response(status_code=204)
    elif request.method == "PROPFIND":
        depth = request.headers.get("Depth", "1")
        depth = 0 if depth == "0" else 1

        resources = browser.propfind(current_path, depth=depth)

        request_path = request.url.path
        if not request_path.endswith("/"):
            request_path += "/"
        xml = templates.render_template("share/webdav.xml", resources=resources, token=token, base_url=request_path)

        return Response(content=xml, status_code=207, media_type="application/xml; charset=utf-8")
    elif request.method == "GET":
        if (path := browser.get_file(current_path)) is None:
            raise exc.NotFoundException(f"File not found: {current_path}")

        if not path.is_file():
            raise exc.BadRequestException("Subpath must be a file")

        mimetype, _ = mimetypes.guess_type(path.name)
        if not mimetype:
            mimetype = "application/octet-stream"

        stat = path.stat()
        return responses.file_response(
            path,
            filename=path.name,
            content_type=mimetype,
            disposition="attachment" if config.settings.ENVIRONMENT != "prod" else None,
            extra_headers={
                "Content-Length": str(stat.st_size),
                "Last-Modified": browser._format_date(stat.st_mtime),
            },
        )
    else:
        raise exc.MethodNotAllowedException()
