from dataclasses import dataclass
from pathlib import Path
import mimetypes

from flask import Blueprint, render_template, Response, send_from_directory

from .... import db, logger, DEBUG
from ....core import wrappers, exceptions
from ....tools import utils
from ....core.RunTime import runtime

file_share_bp = Blueprint("file_share", __name__, url_prefix="/api/files/")


@dataclass
class SharePath:
    name: str
    path: Path


class SharedFileBrowser:
    def __init__(self, shares: list[str], share_root_dir: Path):
        self.share_root_dir = share_root_dir
        self.shares = [self.share_root_dir / share for share in shares]
        
    def list_contents(self, subpath: Path | str = Path()) -> list[SharePath]:
        if isinstance(subpath, str):
            subpath = Path(subpath)

        paths = []
        if subpath == Path():
            for share in self.shares:
                paths.append(SharePath(
                    name=share.name,
                    path=share,
                ))
            
            return paths

        for share in self.shares:
            if share.name == subpath.parts[0]:
                full_path = share / "/".join(subpath.parts[1:])
                if full_path.exists() and full_path.is_dir():
                    for item in full_path.iterdir():
                        paths.append(SharePath(
                            name=item.name,
                            path=item,
                        ))
                return paths
        return []
    
    def get_file(self, subpath: Path | str = Path()) -> SharePath | None:
        if isinstance(subpath, str):
            subpath = Path(subpath)

        for share in self.shares:
            full_path = share / "/".join(subpath.parts[1:])
            if full_path.exists() and full_path.is_file():
                return SharePath(name=full_path.name, path=full_path)
        return None


@wrappers.api_route(file_share_bp, db=db, login_required=False)
def validate(token: str):
    if (share_token := db.shares.get(token)) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
        
    logger.debug(f"File share token verified:\n{'\n\t'.join([path.path for path in share_token.paths])}")
    return "OK", 200


@wrappers.api_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60 if not DEBUG else None, cache_type="global", cache_query_string=True)
def rclone(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token)) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    SHARE_ROOT = Path(runtime.current_app.share_root)

    browser = SharedFileBrowser([path.path for path in share_token.paths], SHARE_ROOT)

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            mimetype = mimetypes.guess_type(file.path)[0] or "application/octet-stream"

            if DEBUG:
                return send_from_directory(file.path.parent, file.name, as_attachment=True, mimetype=mimetype)
            
            response = Response()
            response.headers["Content-Type"] = mimetype
            response.headers["X-Accel-Redirect"] = str(file.path).replace("/usr/src/app/share/", "/nginx-share/")
            return response

    return render_template(
        "share/rclone.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )


@wrappers.page_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60 if not DEBUG else None, cache_type="global", cache_query_string=True)
def browse(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.shares.get(token)) is None:
        raise exceptions.NotFoundException("Token Not Found")
    
    if share_token.is_expired:
        raise exceptions.NoPermissionsException("Token expired")
    
    SHARE_ROOT = Path(runtime.current_app.share_root)

    browser = SharedFileBrowser([path.path for path in share_token.paths], SHARE_ROOT)

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            mimetype = mimetypes.guess_type(file.path)[0] or "application/octet-stream"

            if DEBUG:
                return send_from_directory(file.path.parent, file.name, as_attachment=not utils.is_browser_friendly(mimetype), mimetype=mimetype)
            
            response = Response()
            response.headers["Content-Type"] = mimetype
            if not utils.is_browser_friendly(mimetype):
                response.headers["Content-Disposition"] = f"attachment; filename={file.name}"
            response.headers["X-Accel-Redirect"] = str(file.path).replace("/usr/src/app/share/", "/nginx-share/")
            return response
        
    paths = sorted(paths, key=lambda p: p.name.lower())

    return render_template(
        "share/browse.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )