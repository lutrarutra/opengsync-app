import os
import openpyxl
import mimetypes
from pathlib import Path

import numpy as np
import pandas as pd

from flask import Blueprint, render_template, Response, send_from_directory, request
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import AccessType

from ... import db, logger
from ...tools import utils, FileBrowser
from ...core import wrappers, exceptions
from ...core.RunTime import runtime

files_htmx = Blueprint("files_htmx", __name__, url_prefix="/hmtx/files/")


@wrappers.htmx_route(files_htmx, db=db)
def render_xlsx(current_user: models.User, file_id: int):
    if (file := db.media_files.get(file_id)) is None:
        raise exceptions.NotFoundException()
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.media_files.permissions_check(user_id=current_user.id, file_id=file_id):
            raise exceptions.NoPermissionsException()

    filepath = os.path.join(runtime.app.media_folder, file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        raise exceptions.NotFoundException()
    
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True, rich_text=True)

    sheets = {}
    for sheet_name in wb.sheetnames:
        active_sheet = wb[sheet_name]
        df = pd.DataFrame(active_sheet.values).replace({np.nan: ""})
        df.columns = df.iloc[0]
        df = df.drop(0)
        sheets[sheet_name] = df.to_html(classes="table")

    return make_response(render_template("components/xlsx.html", sheets=sheets, file=file))


@wrappers.resource_route(files_htmx, db=db, login_required=True)
def render_data_file(current_user: models.User, data_path_id: int):
    if (data_path := db.data_paths.get(data_path_id)) is None:
        raise exceptions.NotFoundException("DataPath not found")
    
    if not current_user.is_insider():
        if data_path.project is not None:
            if not db.projects.get_access_type(data_path.project, current_user) < AccessType.VIEW:
                raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
        elif data_path.seq_request is not None:
            if not db.seq_requests.get_access_type(data_path.seq_request, current_user) < AccessType.VIEW:
                raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
        elif data_path.library is not None:
            if not db.libraries.get_access_type(data_path.library, current_user) < AccessType.VIEW:
                raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
        else:
            raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    path = Path(runtime.app.share_root) / data_path.path
    if not path.exists():
        raise exceptions.NotFoundException("Data file not found")
    if not path.is_file():
        raise exceptions.BadRequestException("Data path is not a file")
    
    mimetype = mimetypes.guess_type(path)[0] or "application/octet-stream"

    if runtime.app.debug:
        return send_from_directory(path.parent, path.name, as_attachment=not utils.is_browser_friendly(mimetype), mimetype=mimetype)
    
    response = Response()
    response.headers["Content-Type"] = mimetype
    if not utils.is_browser_friendly(mimetype):
        response.headers["Content-Disposition"] = f"attachment; filename={path.name}"
    response.headers["X-Accel-Redirect"] = path.as_posix().replace(runtime.app.share_root.as_posix(), "/nginx-share/")
    return response


@wrappers.htmx_route(files_htmx, db=db, login_required=True, methods=["GET", "POST"])
def share_path(current_user: models.User):
    from ...forms.workflows.share.AssociatePathForm import AssociatePathForm

    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if (path := request.args.get("path")) is None:
        raise exceptions.BadRequestException("No path specified")
    
    path = Path(path)
    form = AssociatePathForm(path=path, formdata=request.form)
    
    if request.method == "GET":
        return form.make_response()
    
    return form.process_request()

@wrappers.htmx_route(files_htmx, db=db, login_required=True)
def files(current_user: models.User, subpath: Path = Path(), page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permissions to access this resource")
    
    if isinstance(subpath, str):
        subpath = Path(subpath)

    sort_by = request.args.get("sort_by", "name")
    sort_order = request.args.get("sort_order", "asc" if sort_by == "name" else "desc")

    PAGE_LIMIT = 20

    browser = FileBrowser(runtime.app.share_root, db=db)
    paths = browser.list_contents(
        subpath, limit=PAGE_LIMIT, offset=page * PAGE_LIMIT,
        sort_by=sort_by, sort_order=sort_order,  # type: ignore
    )

    return make_response(render_template(
        "components/tables/files-body.html",
        paths=paths,
        current_path=subpath,
        parents_dir=subpath.parent if subpath != Path() else None,
        limit=PAGE_LIMIT, current_page=page,
        sort_by=sort_by, sort_order=sort_order,
    ))

