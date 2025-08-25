import os

from flask import (
    render_template,
    request,
    session,
    make_response,
    flash
)
from flask_htmx import make_response as make_htmx_response

from opengsync_db import models

from ..core import exceptions
from .. import db, logger, flash_cache
from ..core import wrappers
from ..core.RunTime import runtime
from .. import tools


if runtime.current_app.debug:
    @wrappers.page_route(runtime.current_app, db=db, login_required=False)
    def test():
        flash("This is a test flash message.")
        if tools.textgen is not None:
            msg = tools.textgen.generate(
                "You need to write in 1-2 sentences make a joke to greet user to my web runtime.current_app. \
                Only raw text, no special characters (only punctuation , or . or !), no markdown, no code blocks, no quotes, no emojis, no links, no hashtags, no mentions. \
                Just the joke text."
            )
            flash(msg, category="info")
        return render_template("test.html")


@wrappers.page_route(runtime.current_app, login_required=False, cache_timeout_seconds=360, cache_type="global")
def help():
    return render_template("help.html")


@wrappers.htmx_route(runtime.current_app, login_required=False)
def retrieve_flash_messages():
    flashes = flash_cache.consume_all(runtime.session.sid)
    return make_htmx_response(runtime.current_app.no_context_render_template("components/flash.html", flashes=flashes))


@wrappers.page_route(runtime.current_app, db=db, route="/", cache_timeout_seconds=360, cache_type="user")
def dashboard(current_user: models.User):
    if current_user.is_insider():
        return render_template("dashboard-insider.html")
    return render_template("dashboard-user.html")


@wrappers.resource_route(runtime.current_app, db=db)
def pdf_file(file_id: int, current_user: models.User):
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()
    
    if file.extension != ".pdf":
        raise exceptions.BadRequestException()

    filepath = os.path.join(runtime.current_app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException("File not found")
    
    with open(filepath, "rb") as f:
        data = f.read()

    response = make_response(data)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "inline; filename=auth_form.pdf"
    return response


@wrappers.resource_route(runtime.current_app, db=db)
def img_file(current_user: models.User, file_id: int):
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()
    
    if file.extension not in [".png", ".jpg", ".jpeg"]:
        raise exceptions.BadRequestException()

    filepath = os.path.join(runtime.current_app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException()
    
    with open(filepath, "rb") as f:
        data = f.read()

    response = make_response(data)
    response.headers["Content-Type"] = f"image/{file.extension[1:]}"
    response.headers["Content-Disposition"] = "inline; filename={file.name}"
    return response


@wrappers.resource_route(runtime.current_app, db=db)
def download_file(file_id: int, current_user: models.User):
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()

    filepath = os.path.join(runtime.current_app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException()
    
    with open(filepath, "rb") as f:
        data = f.read()

    response = make_response(data)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Content-Disposition"] = f"attachment; filename={file.name}{file.extension}"
    return response


@runtime.current_app.before_request
def before_request():
    session["from_url"] = request.referrer


@wrappers.page_route(runtime.current_app, login_required=False)
def status():
    return make_response("OK", 200)