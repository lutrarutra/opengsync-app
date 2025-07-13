from flask import Response, current_app, url_for, flash
from flask_htmx import make_response
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import FileType

from .... import logger, db  # noqa F401
from ...HTMXFlaskForm import HTMXFlaskForm


class PrepTableForm(HTMXFlaskForm):
    _template_path = "workflows/library_prep/prep_table.html"

    _allowed_extensions: list[tuple[str, str]] = [
        ("xlsx", "Tab-separated"),
    ]

    file = FileField(validators=[OptionalValidator(), FileAllowed([ext for ext, _ in _allowed_extensions])])
    MAX_SIZE_MBYTES = 5

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep