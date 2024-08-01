import os
import io
from typing import TYPE_CHECKING, Literal

import openpyxl
from openpyxl import styles as openpyxl_styles
from openpyxl.utils import get_column_letter

from flask import Blueprint, render_template, request, abort, flash, url_for, current_app, Response
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, PAGE_LIMIT, db_session
from limbless_db.categories import HTTPResponse, LabProtocol

from .... import db, forms, logger  # noqa

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

lab_preps_htmx = Blueprint("lab_preps_htmx", __name__, url_prefix="/api/hmtx/lab_preps/")


@lab_preps_htmx.route("get", methods=["GET"], defaults={"page": 0})
@lab_preps_htmx.route("get/<int:page>", methods=["GET"])
@db_session(db)
@login_required
def get(page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    lab_preps, n_pages = db.get_lab_preps(offset=offset, limit=PAGE_LIMIT, sort_by=sort_by, descending=descending)
    
    return render_template(
        "components/tables/lab_prep.html", lab_preps=lab_preps, n_pages=n_pages, active_page=page,
        sort_by=sort_by, sort_order=sort_order
    )


@lab_preps_htmx.route("get_form/<string:form_type>", methods=["GET"])
@db_session(db)
@login_required
def get_form(form_type: Literal["create", "edit"]):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if form_type not in ["create", "edit"]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (lab_prep_id := request.args.get("lab_prep_id")) is not None:
        try:
            lab_prep_id = int(lab_prep_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if form_type != "edit":
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        return forms.models.LabPrepForm(form_type=form_type, lab_prep=lab_prep).make_response()
    
    # seq_request_id must be provided if form_type is "edit"
    if form_type == "edit":
        return abort(HTTPResponse.BAD_REQUEST.id)

    return forms.models.LabPrepForm(form_type=form_type).make_response()


@lab_preps_htmx.route("create", methods=["POST"])
@db_session(db)
@login_required
def create():
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    form = forms.models.LabPrepForm(formdata=request.form, form_type="create")
    return form.process_request(current_user)


@lab_preps_htmx.route("<int:lab_prep_id>/edit", methods=["POST"])
@db_session(db)
@login_required
def edit(lab_prep_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.models.LabPrepForm(formdata=request.form, form_type="edit", lab_prep=lab_prep)
    return form.process_request(current_user)


@lab_preps_htmx.route("<int:lab_prep_id>/remove_library", methods=["DELETE"])
@db_session(db)
@login_required
def remove_library(lab_prep_id: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if (library_id := request.args.get("library_id")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    try:
        library_id = int(library_id)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    db.remove_library_from_prep(lab_prep_id=lab_prep.id, library_id=library_id)

    flash("Library removed!", "success")
    return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=lab_prep_id))


@lab_preps_htmx.route("<int:lab_prep_id>/get_libraries", methods=["GET"], defaults={"page": 0})
@lab_preps_htmx.route("<int:lab_prep_id>/get_libraries/<int:page>", methods=["GET"])
@db_session(db)
@login_required
def get_libraries(lab_prep_id: int, page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    libraries, n_pages = db.get_libraries(offset=offset, lab_prep_id=lab_prep_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/lab_prep-library.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, lab_prep=lab_prep
        )
    )


@lab_preps_htmx.route("<int:lab_prep_id>/download_template/<string:direction>", methods=["GET"])
@db_session(db)
@login_required
def download_template(lab_prep_id: int, direction: Literal["rows", "columns"]) -> Response:
    if direction not in ("rows", "columns"):
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if current_app.static_folder is None:
        logger.error("Static folder not set")
        raise ValueError("Static folder not set")
    
    if lab_prep.protocol == LabProtocol.RNA_SEQ:
        filepath = os.path.join(current_app.static_folder, "resources", "templates", "library_prep", "RNA.xlsx")
    else:
        filepath = os.path.join(current_app.static_folder, "resources", "templates", "library_prep", "template.xlsx")

    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return abort(HTTPResponse.NOT_FOUND.id)

    template = openpyxl.load_workbook(filepath)

    n = 12 if direction == "rows" else 8
    pattern = [True] * n + [False] * n

    def if_color(i):
        return pattern[i]

    active_sheet = template["prep_table"]
    column_mapping: dict[str, str] = {}
    
    for col_i in range(1, active_sheet.max_column):
        col = get_column_letter(col_i + 1)
        column_name = active_sheet[f"{col}1"].value
        column_mapping[column_name] = col
        
        for row_idx, cell in enumerate(active_sheet[col][1:]):
            if if_color(row_idx % (n * 2)):
                cell.fill = openpyxl_styles.PatternFill(start_color="ced4da", end_color="ced4da", fill_type="solid")
            else:
                cell.fill = openpyxl_styles.PatternFill(start_color="ffffff", end_color="ffffff", fill_type="solid")

    for row_idx, cell in enumerate(active_sheet[column_mapping["plate_well"]][1:]):
        cell.value = models.Plate.well_identifier(row_idx, num_cols=12, num_rows=8, flipped=direction == "columns")

    for row_idx, cell in enumerate(active_sheet[column_mapping["index_well"]][1:]):
        cell.value = models.Plate.well_identifier(row_idx, num_cols=12, num_rows=8, flipped=direction == "columns")
        
    for i, library in enumerate(lab_prep.libraries):
        library_id_cell = active_sheet[f"{column_mapping['library_id']}{i + 2}"]
        library_name_cell = active_sheet[f"{column_mapping['library_name']}{i + 2}"]
        requestor_cell = active_sheet[f"{column_mapping['requestor']}{i + 2}"]
        sequence_i7_cell = active_sheet[f"{column_mapping['sequence_i7']}{i + 2}"]
        sequence_i5_cell = active_sheet[f"{column_mapping['sequence_i5']}{i + 2}"]
        # kit_i7_cell = active_sheet[f"{column_mapping['kit_i7']}{i + 2}"]
        # kit_i5_cell = active_sheet[f"{column_mapping['kit_i5']}{i + 2}"]
        name_i7_cell = active_sheet[f"{column_mapping['name_i7']}{i + 2}"]
        name_i5_cell = active_sheet[f"{column_mapping['name_i5']}{i + 2}"]
        library_id_cell.value = library.id
        library_name_cell.value = library.name
        requestor_cell.value = library.seq_request.requestor.name
        if len(library.indices) > 0:
            name_i7_cell.value = library.indices[0].name_i7
            name_i5_cell.value = library.indices[0].name_i5
        sequence_i7_cell.value = library.sequences_i7_str(";")
        sequence_i5_cell.value = library.sequences_i5_str(";")
        
    bytes_io = io.BytesIO()
    template.save(bytes_io)

    bytes_io.seek(0)
    mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
    return Response(
        bytes_io, mimetype=mimetype,
        headers={"Content-disposition": f"attachment; filename={lab_prep.name}_RNA_{direction}.xlsx"}
    )


@lab_preps_htmx.route("<int:lab_prep_id>/file_upload_form", methods=["GET"])
@db_session(db)
@login_required
def file_upload_form(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.workflows.library_prep.LibraryPrepForm(lab_prep=lab_prep)
    return form.make_response()


@lab_preps_htmx.route("<int:lab_prep_id>/upload_file", methods=["POST"])
@db_session(db)
@login_required
def upload_file(lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    form = forms.workflows.library_prep.LibraryPrepForm(lab_prep=lab_prep, formdata=request.form | request.files)
    
    return form.process_request(user=current_user)


@lab_preps_htmx.route("<int:lab_prep_id>/get_pools/<int:page>", methods=["GET"])
@lab_preps_htmx.route("<int:lab_prep_id>/get_pools", methods=["GET"], defaults={"page": 0})
@login_required
def get_pools(lab_prep_id: int, page: int):
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    pools, n_pages = db.get_pools(
        lab_prep_id=lab_prep_id, offset=offset, sort_by=sort_by, descending=descending
    )

    return make_response(
        render_template(
            "components/tables/lab_prep-pool.html",
            pools=pools, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, lab_prep=lab_prep
        )
    )