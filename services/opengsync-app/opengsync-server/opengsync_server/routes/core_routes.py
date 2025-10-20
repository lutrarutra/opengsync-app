import os

from flask import (
    render_template,
    request,
    session,
    make_response
)
from flask_htmx import make_response as make_htmx_response

from opengsync_db import models

from ..core import exceptions
from .. import db, logger, flash_cache, limiter
from ..core import wrappers
from ..core.RunTime import runtime


if runtime.app.debug:
    @wrappers.page_route(runtime.app, db=db, login_required=False, limit_exempt=None, limit="3 per minute")
    def test(current_user: models.User | None, number: int = 0):
        from ..tools import univer

        if number > 5:
            raise exceptions.NotFoundException()

        if limiter.current_limit:
            logger.debug(limiter.storage.clear(limiter.current_limit.key))

        lab_prep = db.lab_preps[20]
        if not lab_prep.prep_file:
            raise exceptions.BadRequestException("No prep file associated with this lab prep.")
        path = os.path.join(runtime.app.media_folder, lab_prep.prep_file.path)
        snapshot, col_style = univer.xlsx_to_univer_snapshot(path)
        return render_template("test.html", univer_snapshot=snapshot, col_style=col_style)

    @wrappers.page_route(runtime.app, db=db, login_required=True)
    def mail_template(current_user: models.User):
        import premailer

        project = db.projects[14]
        token = project.share_token.uuid  # type: ignore
        http_command = render_template("snippets/rclone-http.sh.j2", token=token)
        sync_command = render_template("snippets/rclone-sync.sh.j2", token=token)
        wget_command = render_template("snippets/wget.sh.j2", token=token)
        style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()

        browse_link = runtime.url_for("file_share.browse", token=token, _external=True)
        seq_requests = db.seq_requests.find(project_id=project.id, limit=None, sort_by="id")[0]
        experiments = db.experiments.find(limit=None, sort_by="id")[0]
        
        content = render_template(
            "email/share-data.html", style=style, browse_link=browse_link,
            tenx_contents=True,
            author=current_user,
            project=project,
            seq_requests=seq_requests,
            experiments=experiments,
            internal_access_share=True,
            share_token=project.share_token,
            share_path_mapping={"ok2": "replaced"},
            http_command=http_command,
            sync_command=sync_command,
            wget_command=wget_command,
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
    if (file := db.media_files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.media_files.permissions_check(user_id=current_user.id, file_id=file_id):
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
    if (file := db.media_files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.media_files.permissions_check(user_id=current_user.id, file_id=file_id):
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
    if (file := db.media_files.get(file_id)) is None:
        raise exceptions.NotFoundException()

    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.media_files.permissions_check(user_id=current_user.id, file_id=file_id):
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


@wrappers.api_route(runtime.app, login_required=False)
def status():
    return make_response("OK", 200)


@wrappers.api_route(runtime.app, login_required=False)
def headers():
    logger.info(request.headers)
    return make_response("OK", 200)
