import json

import pandas as pd

from flask import Response, flash, url_for
from flask_wtf.file import FileField, FileAllowed
from flask_htmx import make_response
from wtforms.validators import NumberRange, DataRequired
from wtforms import StringField
from flask_wtf import FlaskForm

from opengsync_db import models

from .... import db, logger
from ....core.RunTime import runtime
from ...MultiStepForm import MultiStepForm
from .CompleteBAForm import CompleteBAForm


class ParseBAExcelFile(MultiStepForm):
    _template_path = "workflows/ba_report/bar-2.html"
    _workflow_name = "ba_report"
    _step_name = "parse_ba_excel_file"

    left_order = StringField()
    right_order = StringField()

    def __init__(self, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=ParseBAExcelFile._workflow_name,
            step_name=ParseBAExcelFile._step_name, uuid=uuid,
            formdata=formdata,
            step_args={}
        )
        self.excel_table = self.tables["excel_table"]
        self.sample_table = self.tables["sample_table"]

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.left_order.data is None:
            logger.error("Left order is None")
            return False
        if self.right_order.data is None:
            logger.error("Right order is None")
            return False
        
        try:
            self.samples_order = [int(s) for s in json.loads(self.left_order.data)]
        except ValueError:
            self.left_order.errors = ("Invalid format. Please, provide a comma-separated list of integers.",)
            return False
        
        try:
            data = json.loads(self.right_order.data)
            self.excel_order = [
                (str(s["name"]), int(s["value"]))
                for s in data
            ]
        except ValueError:
            self.right_order.errors = ("Invalid format. Please, provide a comma-separated list of integers.",)
            return False
        
        return True

    def process_request(self) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()
        
        data = {
            "id": [],
            "name": [],
            "sample_type": [],
            "avg_fragment_size": [],
            "well_name": [],
        }

        for i in range(min(len(self.samples_order), len(self.excel_order))):
            sample_idx = self.samples_order[i]
            excel_name, excel_value = self.excel_order[i]

            data["id"].append(self.sample_table.at[sample_idx, "id"])
            data["name"].append(self.sample_table.at[sample_idx, "name"])
            data["sample_type"].append(self.sample_table.at[sample_idx, "sample_type"])
            data["avg_fragment_size"].append(excel_value)
            data["well_name"].append(excel_name)

        ba_table = pd.DataFrame(data)
        self.add_table("ba_table", ba_table)
        self.update_data()
        form = CompleteBAForm(uuid=self.uuid)
        return form.make_response()