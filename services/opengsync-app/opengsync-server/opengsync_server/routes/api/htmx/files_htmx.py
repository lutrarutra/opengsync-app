import os
import openpyxl

import numpy as np
import pandas as pd

from flask import Blueprint, render_template, abort
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse

from .... import db, logger
from ....core import wrappers
from ....core.RunTime import runtime

files_htmx = Blueprint("files_htmx", __name__, url_prefix="/api/hmtx/files/")


@wrappers.htmx_route(files_htmx, db=db)
def render_xlsx(current_user: models.User, file_id: int):
    if (file := db.files.get(file_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if file.uploader_id != current_user.id and not current_user.is_insider():
        if not db.files.permissions_check(user_id=current_user.id, file_id=file_id):
            return abort(HTTPResponse.FORBIDDEN.id)

    filepath = os.path.join(runtime.current_app.media_folder, file.path)
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
