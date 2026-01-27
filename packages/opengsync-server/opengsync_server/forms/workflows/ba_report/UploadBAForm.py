import io
import re
import tempfile
from typing import Literal

import pandas as pd

from flask import Response, flash, url_for
from flask_wtf.file import FileField, FileAllowed
from flask_htmx import make_response
from wtforms.validators import NumberRange, DataRequired, Optional as OptionalValidator
from wtforms import IntegerField, FieldList, FormField, StringField
from flask_wtf import FlaskForm

from opengsync_db import models

from .... import db, logger  # noqa
from ....core import exceptions
from ...MultiStepForm import MultiStepForm
from .ParseBAExcelFile import ParseBAExcelFile


class SubForm(FlaskForm):
    obj_id = IntegerField(validators=[DataRequired()])
    sample_type = StringField(validators=[DataRequired()])
    avg_fragment_size = IntegerField(validators=[OptionalValidator(), NumberRange(min=0)])


class UploadBAForm(MultiStepForm):
    _template_path = "workflows/ba_report/bar-1.html"
    _workflow_name = "ba_report"
    _step_name = "upload_ba_report"

    _allowed_extensions: list[tuple[str, str]] = [
        ("pdf", "PDF"),
    ]

    sample_fields = FieldList(FormField(SubForm), min_entries=0)

    pdf = FileField("Bio Analyzer Report", validators=[FileAllowed([ext for ext, _ in _allowed_extensions])], description="Report exported from the BioAnalyzer software (pdf).")
    excel = FileField("Excel", validators=[FileAllowed(["csv"], "CSV files only!")])

    def __init__(self, uuid: str | None, formdata: dict | None = None, method: Literal["manual", "excel"] | None = None, max_size_mbytes: int = 5):
        MultiStepForm.__init__(
            self, workflow=UploadBAForm._workflow_name,
            step_name=UploadBAForm._step_name, uuid=uuid, formdata=formdata,
            step_args={}
        )
        self.method = method
        self.max_size_mbytes = max_size_mbytes
        self._context["enumerate"] = enumerate
        self.sample_table = self.tables["sample_table"]
        self._context["active_tab"] = "manual" if self.method == "manual" else "excel"

    def prepare(self):
        for i, (idx, row) in enumerate(self.sample_table.iterrows()):
            if i > len(self.sample_fields) - 1:
                self.sample_fields.append_entry()

            self.sample_fields[i].obj_id.data = int(row["id"])
            self.sample_fields[i].sample_type.data = row["sample_type"]

            if pd.notna(fragment_size := self.sample_table.at[idx, "avg_fragment_size"]):
                self.sample_fields[i].avg_fragment_size.data = int(fragment_size)
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.method == "manual":
            self._context["active_tab"] = "manual"
            if self.pdf.data is None:
                self.pdf.errors = ("Bio Analyzer Report is Required",)
                return False
            
            max_bytes = self.max_size_mbytes * 1024 * 1024
            size_bytes = len(self.pdf.data.read())
            self.pdf.data.seek(0)

            if size_bytes > max_bytes:
                self.pdf.errors = (f"File size exceeds {self.max_size_mbytes} MB",)
                return False
            
        elif self.method == "excel":
            self._context["active_tab"] = "excel"
            if self.excel.data is None:
                self.excel.errors = ("Excel is Required",)
                return False
        else:
            logger.error(f"{self.uuid}: Invalid method {self.method}")
            raise exceptions.InternalServerErrorException()
        
        return True
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()

        if self.method == "excel":
            data = {
                "sample_name": [],
                "avg_fragment_size": [],
            }
            
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
                self.excel.data.save(f)
                excel_content = open(f.name, "r", encoding="latin-1").read()
            
            for it in re.finditer(r"Sample Name,([^\r\n]+)(?:\s*Peak Table\n([\s\S]*?))(?:\s*Region Table\n([\s\S]*?))(?=\nSample Name,|\s*$)", excel_content):
                sample_name = it.group(1).strip()
                logger.debug(sample_name)
                _ = it.group(2).strip()
                region_table = it.group(3).strip()
                data["sample_name"].append(sample_name)
                try:
                    data["avg_fragment_size"].append(int(pd.read_csv(io.StringIO(region_table), encoding="latin-1")["Average Size [bp]"].values[0]))
                except ValueError:
                    data["avg_fragment_size"].append(None)

            df = pd.DataFrame(data)
            if df.empty:
                self.excel.errors = ("No valid data was parsed in the Excel file.",)
                return self.make_response()
            self.add_table("excel_table", df)
            self.update_data()
            form = ParseBAExcelFile(uuid=self.uuid)
            return form.make_response()
        
        from .CompleteBAForm import CompleteBAForm
        CompleteBAForm.save_changes(
            user=user,
            metadata=self.metadata,
            report=self.pdf,
            uuid=self.uuid,
            sample_fields=self.sample_fields,  # type: ignore
        )

        self.complete()
        flash("Bio Analyzer report saved!", "success")
        if (experiment_id := self.metadata.get("experiment_id")) is not None:
            url = url_for("experiments_page.experiment", experiment_id=experiment_id)
        elif (seq_request_id := self.metadata.get("seq_request_id")) is not None:
            url = url_for("seq_requests_page.seq_request", seq_request_id=seq_request_id)
        elif (pool_id := self.metadata.get("pool_id")) is not None:
            url = url_for("pools_page.pool", pool_id=pool_id)
        elif (lab_prep_id := self.metadata.get("lab_prep_id")) is not None:
            url = url_for("lab_preps_page.lab_prep", lab_prep_id=lab_prep_id)
        else:
            url = url_for("dashboard")

        return make_response(redirect=url)
