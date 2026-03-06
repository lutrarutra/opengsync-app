from pathlib import Path
import mimetypes
from typing import Literal
import zipstream.ng as zipstream

from sqlalchemy import orm

from flask import Blueprint, render_template, Response, send_from_directory, stream_with_context

from opengsync_db import models

from ... import db, DEBUG, limiter, logger
from ...core import wrappers, exceptions
from ...tools import utils, SharedFileBrowser
from ...core.RunTime import runtime

file_share_bp = Blueprint("file_share", __name__, url_prefix="/files/share/")


@wrappers.api_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20/minute", api_token_required=False)
def validate(token: str):
    if (share_token := db.shares.get(token)) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
        
    return "OK", 200


@wrappers.api_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=300, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20/minute", api_token_required=False)
def rclone(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    runtime.session["clear_rate_limit"] = True

    SHARE_ROOT = runtime.app.share_root

    browser = SharedFileBrowser(root_dir=SHARE_ROOT, db=db, share_token=share_token)

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            mimetype = mimetypes.guess_type(file)[0] or "application/octet-stream"

            if DEBUG:
                return send_from_directory(file.parent, file.name, as_attachment=True, mimetype=mimetype)
            
            response = Response()
            response.headers["Content-Type"] = mimetype
            response.headers["X-Accel-Redirect"] = file.as_posix().replace(SHARE_ROOT.as_posix(), "/nginx-share/")
            return response

    return render_template(
        "share/rclone.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )


@wrappers.resource_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20/minute")
def browse(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    runtime.session["clear_rate_limit"] = True

    SHARE_ROOT = runtime.app.share_root

    browser = SharedFileBrowser(root_dir=SHARE_ROOT, db=db, share_token=share_token)

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
        
    paths = sorted(paths, key=lambda p: p.name.lower())

    return render_template(
        "share/browse.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )

@wrappers.resource_route(file_share_bp, db=db, login_required=False, strict_slashes=False, limit="3/minute")
def download_archive(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)
    
    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    SHARE_ROOT = runtime.app.share_root
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, db=db, share_token=share_token)

    if not browser.is_safe(subpath):
        raise exceptions.NoPermissionsException("Invalid path")

    def generate_zip():
        zs = zipstream.ZipStream(compress_type=zipstream.ZIP_STORED)

        for rel_path, is_dir in browser.walk_contents(subpath):
            if is_dir:
                continue
            
            abs_path = SHARE_ROOT / rel_path
            
            try:
                arcname = rel_path.relative_to(subpath.parent)
            except ValueError:
                arcname = rel_path

            zs.add_path(str(abs_path), arcname.as_posix())

        yield from zs

    filename = f"{subpath.name or 'archive'}.zip"
    
    return Response(
        stream_with_context(generate_zip()),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@wrappers.htmx_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20/minute")
def rclone_script(token: str):
    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    sync_command = render_template("snippets/rclone-sync.sh.j2", token=share_token.uuid, outdir="outdir")
    return sync_command, 200, {"Content-Type": "text/plain"}


@wrappers.resource_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60, cache_type="global", cache_query_string=True, limit_override=True, limit_exempt=None, limit="20/minute")
def curl_script(token: str, platform: Literal["windows", "unix"]):
    if platform == "unix":
        template = "snippets/curl-download.sh.j2"
    elif platform == "windows":
        template = "snippets/curl-download.ps1.j2"
    else:
        raise exceptions.BadRequestException("Invalid platform")
    
    if (share_token := db.shares.get(token, options=orm.selectinload(models.ShareToken.paths))) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    
    SHARE_ROOT = runtime.app.share_root
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, db=db, share_token=share_token)
    subpath = Path()
    items = []
    for rel_path, is_dir in browser.walk_contents(subpath):
        try:
            display_path = rel_path.relative_to(subpath) if subpath != Path() else rel_path
        except ValueError:
            display_path = rel_path
            
        url = runtime.url_for('file_share.rclone', token=token, subpath=rel_path.as_posix(), _external=True)
        
        items.append({
            'rel_path': display_path.as_posix(),
            'is_dir': is_dir,
            'url': url
        })

    rendered_script = render_template(
        template, base_folder=subpath.name if subpath.name else "download", items=items
    )

    return Response(
        rendered_script,
        mimetype="text/x-shellscript",
        headers={"Content-Disposition": f"attachment; filename=sync_{subpath.name or 'all'}.sh"}
    )