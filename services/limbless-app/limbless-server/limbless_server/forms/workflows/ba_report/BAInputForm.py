import os
import uuid
from typing import Optional

from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import DataRequired
from flask import Response

from limbless_db import models
from limbless_db.categories import FileType

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .CompleteBAReportForm import CompleteBAReportForm


class BAInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/ba_report/bar-2.html"
    _form_label = "ba_report_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("pdf", "PDF"),
    ]

    file = FileField(validators=[DataRequired(), FileAllowed([ext for ext, _ in _allowed_extensions])])

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None, max_size_mbytes: int = 5, experiment: Optional[models.Experiment] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="ba_report", uuid=uuid)
        self.max_size_mbytes = max_size_mbytes
        self.experiment = experiment

    def prepare(self):
        self._context["pool_table"] = self.tables["pool_table"]

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        max_bytes = self.max_size_mbytes * 1024 * 1024
        size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {self.max_size_mbytes} MB",)
            return False
        
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            pool_table = self.tables["pool_table"]
            return self.make_response(pool_table=pool_table)
        
        filename, extension = os.path.splitext(self.file.data.filename)
        
        _uuid = str(uuid.uuid4())
        filepath = os.path.join(self._dir, f"{_uuid}{extension}")
        self.file.data.save(filepath)

        self.metadata["ba_report"] = {
            "filename": filename,
            "extension": extension,
            "uuid": _uuid,
        }
        if self.experiment is not None:
            self.metadata["experiment_id"] = self.experiment.id

        self.update_data()

        ba_report_form = CompleteBAReportForm(uuid=self.uuid, previous_form=self)
        ba_report_form.prepare()
        return ba_report_form.make_response()