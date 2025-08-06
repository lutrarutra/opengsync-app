import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, current_app, request, render_template, send_from_directory
from itsdangerous import BadSignature, SignatureExpired

from opengsync_db.categories import HTTPResponse

from .... import db, logger, serializer
from ....core import wrappers
from ....core import tokens

file_share_bp = Blueprint("file_share", __name__, url_prefix="/api/files/")


if os.getenv("OPENGSYNC_DEBUG") == "1":
    @wrappers.api_route(file_share_bp, db=db, login_required=False)
    def generate(path: Path):
        if isinstance(path, str):
            path = Path(path)

        if not os.path.exists(current_app.config["SHARE_ROOT"] / path):
            return "Path does not exist", HTTPResponse.BAD_REQUEST.id
        
        token = tokens.generate_file_share_token(str(path), serializer)
        logger.debug("Generated file share token", extra={"path": path, "token": token})
        
        return {"token": token}, HTTPResponse.OK.id


@wrappers.api_route(file_share_bp, login_required=False)
def validate(token: str):
    try:
        path = tokens.verify_file_share_token(token, max_age_hours=1, serializer=serializer)
    except SignatureExpired:
        return "Token expired, please request a new token..", HTTPResponse.BAD_REQUEST.id
    except BadSignature:
        return "Invalid token", HTTPResponse.BAD_REQUEST.id

    logger.debug(f"File share token verified: {path}", extra={"path": path})
    return "OK", HTTPResponse.OK.id


@wrappers.page_route(file_share_bp, login_required=False, debug=True, strict_slashes=False)
def browse(token: str, subpath: Path = Path("")):
    if isinstance(subpath, str):
        subpath = Path(subpath)

    logger.debug(subpath)

    try:
        path = tokens.verify_file_share_token(token, max_age_hours=1, serializer=serializer)
    except SignatureExpired:
        return "Token expired, please request a new token..", HTTPResponse.BAD_REQUEST.id
    except BadSignature:
        return "Invalid token", HTTPResponse.BAD_REQUEST.id
    
    if path is None:
        return "Invalid token", HTTPResponse.BAD_REQUEST.id

    rclone = "rclone" in (request.headers.get("User-Agent") or "").lower() or "rclone" in request.args.get("agent", "").lower()
    # Join the base directory with the requested subpath safely
    abs_path = Path(current_app.config["SHARE_ROOT"]) / path / subpath

    # Normalize the path to prevent directory traversal attacks
    abs_path = abs_path.resolve()

    # Verify the path is within the allowed directory
    abs_root = Path(current_app.config["SHARE_ROOT"]).resolve()
    if not abs_path.is_relative_to(abs_root):
        return "Access denied", HTTPResponse.FORBIDDEN.id
    
    # Check if path exists
    if not abs_path.exists():
        return "Not found", HTTPResponse.NOT_FOUND.id

    # If it's a file, send it for download/viewing
    if abs_path.is_file():
        return send_from_directory(abs_path.parent, abs_path.name, as_attachment=False)

    # If it's a directory, list its contents
    files = []
    dirs = []
    for item in abs_path.iterdir():
        if item.is_dir():
            dirs.append({
                'name': item.name,
                'size': '-',
                'modified': datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
        else:
            files.append({
                'name': item.name,
                'size': item.stat().st_size,
                'modified': datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
    
    # Sort directories and files separately
    dirs.sort(key=lambda x: x['name'])
    files.sort(key=lambda x: x['name'])
    
    # Get parent directory
    parent_dir = subpath.parent
    logger.debug(parent_dir)
    logger.debug(subpath)
    if parent_dir == subpath or parent_dir == Path('.'):
        parent_dir = ''

    # Render the template
    return render_template(
        "browse.html", current_path=subpath,
        parent_dir=parent_dir, directories=dirs, files=files,
        rclone=rclone, token=token
    )