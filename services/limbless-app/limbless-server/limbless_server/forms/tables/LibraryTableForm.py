from flask import Response, abort
from wtforms import FieldList, FormField, IntegerField
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import HTTPResponse

from .TableColForm import TableColForm
from ..HTMXFlaskForm import HTMXFlaskForm
from ... import db


class LibraryTableForm(FlaskForm, HTMXFlaskForm):
    _template_path = "components/tables/library.html"
    _form_label = "library_table_form"

    columns = FieldList(FormField(TableColForm), min_entries=1)
    page = IntegerField(validators=[DataRequired()], default=0)

    def process_request(self, current_user: models.User) -> Response:
        if not self.validate():
            return abort(HTTPResponse.BAD_REQUEST.id)

        libraries, n_pages = db.get_libraries(
            user_id=current_user.id if not current_user.is_insider() else None,
            sort_by=sort_by, descending=descending,
            status_in=status_in, type_in=type_in, offset=offset,
        )

        return self.make_response(
            libraries=libraries,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            status_in=status_in, type_in=type_in
        )