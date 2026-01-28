import os

from flask import (
    jsonify,
    render_template,
    request,
    make_response,
)

from opengsync_db import models

from ..core import exceptions, wrappers
from ..tools import utils, univer
from ..core.RunTime import runtime
from .. import db, logger, flash_cache


if runtime.app.debug:
    @wrappers.page_route(runtime.app, db=db, login_required=True)
    def test():
        runtime.app.add_praise(
            "Sequencing Request Submitted for Review!",
            render_template("components/after-seq_request-submit-info.html", email="hello@test.com")
        )
        return render_template("test.html")
    
    @wrappers.htmx_route(runtime.app, db=db, login_required=True)
    def htmx_test():
        raise exceptions.NotFoundException()

    @wrappers.page_route(runtime.app, db=db, login_required=True)
    def mail_template(current_user: models.User):
        import premailer

        project = db.projects["BSA_1059"]
        outdir = "outdir"
        token = project.share_token.uuid  # type: ignore
        http_command = render_template("snippets/rclone-http.sh.j2", token=token, outdir=outdir)
        sync_command = render_template("snippets/rclone-sync.sh.j2", token=token, outdir=outdir)
        wget_command = render_template("snippets/wget.sh.j2", token=token, outdir=outdir)
        style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()

        browse_link = runtime.url_for("file_share.browse", token=token, _external=True)
        seq_requests = db.seq_requests.find(project_id=project.id, limit=None, sort_by="id")[0]
        experiments = db.experiments.find(project_id=project.id, limit=None, sort_by="id")[0]

        internal_share_content = ""
        if (template := runtime.app.personalization.get("internal_share_template")):
            if os.path.exists(os.path.join(runtime.app.template_folder, template)):
                internal_paths = project.data_paths
                internal_paths = utils.filter_subpaths([data_path.path for data_path in internal_paths])
                internal_paths = [utils.replace_substrings(path, runtime.app.share_path_mapping) for path in internal_paths]
                internal_share_content = render_template(
                    template, paths=internal_paths, project=project
                )
            else:
                logger.info(f"Internal share template '{template}' not found.")
            
        content = render_template(
            "email/share-data.html", style=style, browse_link=browse_link,
            tenx_contents=True,
            internal_share_content=internal_share_content,
            author=current_user,
            project=project,
            seq_requests=seq_requests,
            experiments=experiments,
            internal_access_share=True,
            share_token=project.share_token,
            http_command=http_command,
            sync_command=sync_command,
            wget_command=wget_command,
            outdir=outdir
        )

        content = premailer.transform(content)
        return content

@wrappers.api_route(runtime.app, db=db, methods=["GET"], json_params=["api_token"], limit="3/second", limit_override=True, api_token_required=False)
def validate_api_token(api_token: str):
    if (token := db.api_tokens.get(api_token)) is None:
        raise exceptions.NotFoundException("API token not found.")
    
    if token.is_expired:
        raise exceptions.NoPermissionsException("API token is expired.")
    
    return jsonify({"result": "success", "owner_id": token.owner_id, "token_id": token.id, "owner_email": token.owner.email}), 200

@wrappers.page_route(runtime.app, db=db, login_required=False, cache_timeout_seconds=1000, cache_type="user")
def help():
    return render_template("help.html")

@wrappers.api_route(runtime.app, login_required=False, track_usage=False, api_token_required=False, limit="10/second", limit_override=True)
def retrieve_flash_messages():
    if runtime.session.sid is not None:
        if (flashes := flash_cache.consume_all(runtime.session.sid)) is not None:
            return jsonify(flashes), 200
    return jsonify({}), 204

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
    response.headers["Content-Disposition"] = f"inline; filename={file.name}.pdf"
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

@wrappers.resource_route(runtime.app, db=db)
def xlsx_data(current_user: models.User, file_id: int):
    if (file := db.media_files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.media_files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()

    filepath = os.path.join(runtime.app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException()
    
    if not filepath.lower().endswith((".xlsx", ".xls")):
        raise exceptions.BadRequestException("File is not an Excel file")
    
    data, style = univer.xlsx_to_univer_snapshot(filepath)
    return jsonify({"data": data, "style": style}), 200


@wrappers.api_route(runtime.app, login_required=False, api_token_required=False, limit="5/second", limit_override=True, track_usage=False)
def status():
    return make_response("OK", 200)


@wrappers.api_route(runtime.app, login_required=False, api_token_required=False, track_usage=False)
def headers():
    logger.info(request.headers)
    logger.info(request.headers.get("X-Real-IP", request.remote_addr, type=str))
    logger.info(request.headers.get("X-Real-IP"))
    return make_response("OK", 200)
