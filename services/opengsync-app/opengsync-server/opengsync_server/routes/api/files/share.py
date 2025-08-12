import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, request, render_template, send_from_directory, Response

from opengsync_db.categories import HTTPResponse
from opengsync_db import DBHandler, models

from .... import db, logger, cache
from ....core import wrappers

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


@wrappers.api_route(file_share_bp, db=db)
def validate(token: str):
    if (share_token := db.get_share_token(token)) is None:
        return "Token Not Found", HTTPResponse.NOT_FOUND.id
    
    if share_token.is_expired:
        return "Token expired", HTTPResponse.BAD_REQUEST.id
        
    logger.debug(f"File share token verified:\n{'\n\t'.join([path.path for path in share_token.paths])}")
    return "OK", HTTPResponse.OK.id


@wrappers.api_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60)
def rclone(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.get_share_token(token)) is None:
        return "Token Not Found", HTTPResponse.NOT_FOUND.id
    
    if share_token.is_expired:
        return "Token expired", HTTPResponse.BAD_REQUEST.id
    
    SHARE_ROOT = Path(current_app.config["SHARE_ROOT"])

    browser = SharedFileBrowser([path.path for path in share_token.paths], SHARE_ROOT)

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            response = Response()
            response.headers["X-Accel-Redirect"] = str(file.path).replace("/usr/src/app/share/", "/nginx-share/")
            return response

    return render_template(
        "share/rclone.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )

@wrappers.page_route(file_share_bp, db=db, login_required=False, strict_slashes=False, cache_timeout_seconds=60)
def browse(token: str, subpath: Path = Path()):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    if (share_token := db.get_share_token(token)) is None:
        return "Token Not Found", HTTPResponse.NOT_FOUND.id
    
    if share_token.is_expired:
        return "Token expired", HTTPResponse.BAD_REQUEST.id
    
    SHARE_ROOT = Path(current_app.config["SHARE_ROOT"])

    browser = SharedFileBrowser([path.path for path in share_token.paths], SHARE_ROOT)

    if len(paths := browser.list_contents(subpath)) == 0:
        if (file := browser.get_file(subpath)) is not None:
            response = Response()
            response.headers["X-Accel-Redirect"] = str(file.path).replace("/usr/src/app/share/", "/nginx-share/")
            return response

    return render_template(
        "share/browse.html", current_path=subpath,
        parent_dir=subpath.parent if subpath != Path() else None,
        paths=paths, token=token
    )