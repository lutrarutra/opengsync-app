import os
import openpyxl
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from flask import Blueprint, render_template, request, abort, flash, url_for, current_app
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT, db_session
from limbless_db.categories import HTTPResponse, PoolStatus, LibraryStatus

from .... import db, forms, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

files_htmx = Blueprint("files_htmx", __name__, url_prefix="/api/hmtx/files/")


@files_htmx.route("<int:file_id>/render_xlsx", methods=["GET"])
@login_required
def render_xlsx(file_id: int):
    if (file := db.get_file(file_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
            return abort(HTTPResponse.FORBIDDEN.id)

    filepath = os.path.join(current_app.config["MEDIA_FOLDER"], file.path)
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return abort(HTTPResponse.NOT_FOUND.id)
    
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True, rich_text=True)

    sheets = {}
    for sheet_name in wb.sheetnames:
        active_sheet = wb[sheet_name]
        df = pd.DataFrame(active_sheet.values).replace({np.nan: ""})
        df.columns = df.iloc[0]
        df = df.drop(0)
        sheets[sheet_name] = df.to_html(classes="table")

    return make_response(render_template("components/xlsx.html", sheets=sheets, file=file))
