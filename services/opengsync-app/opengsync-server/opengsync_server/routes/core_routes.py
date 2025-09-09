import os

from flask import (
    render_template,
    request,
    session,
    make_response,
    url_for
)
from flask_htmx import make_response as make_htmx_response
from flask_limiter.util import get_remote_address

from opengsync_db import models

from ..core import exceptions
from .. import db, logger, flash_cache, limiter
from ..core import wrappers
from ..core.RunTime import runtime


if runtime.app.debug:
    @wrappers.page_route(runtime.app, db=db, login_required=False, limit_exempt=None, limit="3 per minute")
    def test(current_user: models.User | None, number: int):
        logger.debug(get_remote_address())

        if number > 5:
            raise exceptions.NotFoundException()

        if limiter.current_limit:
            logger.debug(limiter.storage.clear(limiter.current_limit.key))

        return render_template("test.html")

    @wrappers.page_route(runtime.app, db=db, login_required=True)
    def mail_template(current_user: models.User):
        import premailer

        download_command = render_template("snippets/rclone-copy.sh.j2", token="aisndnasdnuasndu")
        style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()

        browse_link = url_for("file_share.browse", token="aisndnasdnuasndu", _external=True)

        content = render_template(
            "email/share-data.html", style=style, download_command=download_command, browse_link=browse_link,
            tenx_contents=True,
            author=current_user
        )

        content = premailer.transform(content)
        return content


@wrappers.page_route(runtime.app, db=db, login_required=False, cache_timeout_seconds=1000, cache_type="global")
def help():
    return render_template("help.html")


@wrappers.htmx_route(runtime.app, login_required=False)
def retrieve_flash_messages():
    flashes = flash_cache.consume_all(runtime.session.sid)
    return make_htmx_response(runtime.app.no_context_render_template("components/flash.html", flashes=flashes))


@wrappers.page_route(runtime.app, db=db, route="/", cache_timeout_seconds=360, cache_type="user")
def dashboard(current_user: models.User):
    if current_user.is_insider():
        return render_template("dashboard-insider.html")
    return render_template("dashboard-user.html")


@wrappers.resource_route(runtime.app, db=db)
def pdf_file(file_id: int, current_user: models.User):
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()

    if file.extension != ".pdf":
        raise exceptions.BadRequestException()

    filepath = os.path.join(runtime.app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException("File not found")

    with open(filepath, "rb") as f:
        data = f.read()

    response = make_response(data)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "inline; filename=auth_form.pdf"
    return response


@wrappers.resource_route(runtime.app, db=db)
def img_file(current_user: models.User, file_id: int):
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()

    if file.extension not in [".png", ".jpg", ".jpeg"]:
        raise exceptions.BadRequestException()

    filepath = os.path.join(runtime.app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException()

    with open(filepath, "rb") as f:
        data = f.read()

    response = make_response(data)
    response.headers["Content-Type"] = f"image/{file.extension[1:]}"
    response.headers["Content-Disposition"] = "inline; filename={file.name}"
    return response


@wrappers.resource_route(runtime.app, db=db)
def download_file(file_id: int, current_user: models.User):
    if (file := db.files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()

    filepath = os.path.join(runtime.app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException()

    with open(filepath, "rb") as f:
        data = f.read()

    response = make_response(data)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Content-Disposition"] = f"attachment; filename={file.name}{file.extension}"
    return response


@runtime.app.before_request
def before_request():
    session["from_url"] = request.referrer


@wrappers.page_route(runtime.app, login_required=False)
def status():
    return make_response("OK", 200)
