import string
import json
from typing import Literal

import pandas as pd
import numpy as np

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import AttributeType

from .. import logger, db  # noqa F401
from ..tools import SpreadSheetColumn
from .HTMXFlaskForm import HTMXFlaskForm


class SampleAttributeTableForm(HTMXFlaskForm):
    _template_path = "forms/sample_attribute_table_form.html"
    _form_label = "sample_attribute_table_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
    }

    predefined_columns = {"sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str)} | dict([(t.label, SpreadSheetColumn(string.ascii_uppercase[i + 1], t.label, t.name, "text", 100, str)) for i, t in enumerate(AttributeType.as_list()) if t.label != "custom"])
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, project: models.Project, formdata: dict = {}):
        super().__init__(formdata=formdata)
        self.project = project

        self._context["project"] = project
        self._context["colors"] = SampleAttributeTableForm.colors
        self._context["spreadsheet_style"] = {}
        self.df = db.get_project_sample_attributes_df(self.project.id)
        self.spreadsheet_df = self.df.copy()

    def prepare(self):
        columns = []
        for i, col in enumerate(self.spreadsheet_df.columns):
            if "id" == col:
                width = 50
            elif "name" == col:
                width = 300
            else:
                width = 150
            columns.append(SpreadSheetColumn(
                string.ascii_uppercase[i], col, col.replace("_", " ").title(), "text", width, var_type=str
            ))

        self._context["spreadsheet_data"] = self.spreadsheet_df.replace({np.nan: ""}).values.tolist()
        self._context["columns"] = columns

    def validate(self) -> bool:
        if not super().validate() or self.formdata is None:
            return False
        
        if (data := self.formdata["data"]) is None:
            self.spreadsheet_dummy.errors = ("No data provided",)
            return False
        
        if (columns := self.formdata["columns"]) is None:
            self.spreadsheet_dummy.errors = ("No columns provided",)
            return False
        
        data = json.loads(data)  # type: ignore
        
        try:
            self.spreadsheet_df = pd.DataFrame(data)
            self.spreadsheet_df.columns = [col.lower().strip().replace(" ", "_") for col in json.loads(columns).split(",")]
        except ValueError as e:
            self.spreadsheet_dummy.errors = (str(e),)
            return False
        
        if "id" not in self.spreadsheet_df.columns:
            self.spreadsheet_dummy.errors = ("Missing 'id' column",)
            return False
        
        if "name" not in self.spreadsheet_df.columns:
            self.spreadsheet_dummy.errors = ("Missing 'name' column",)
            return False

        _df = self.spreadsheet_df.drop(columns=["id", "name"])
        if _df.columns.str.len().min() < 3:
            shortest_col = _df.columns[_df.columns.str.len() == _df.columns.str.len().min()].values[0]
            self.spreadsheet_dummy.errors = (f"Column: '{shortest_col}', specify more descriptive column name by right-clicking column and 'Rename this column'",)
            return False

        if self.spreadsheet_df.columns.duplicated().any():
            self.spreadsheet_dummy.errors = ("Duplicate column names",)
            return False
        
        self.spreadsheet_dummy.errors = []
        column_order = self.spreadsheet_df.columns.tolist()

        logger.debug(self.spreadsheet_df)
        logger.debug(self.df)

        logger.debug(self.spreadsheet_df["id"].values)
        logger.debug(self.df["id"].values)

        def add_error(row_num: int, column: str, message: str, color: Literal["missing_value", "invalid_value", "duplicate_value"]):
            self._context["spreadsheet_style"][f"{string.ascii_uppercase[column_order.index(column)]}{row_num}"] = f"background-color: {SampleAttributeTableForm.colors[color]};"
            self.spreadsheet_dummy.errors.append(f"Row {row_num}: {message}")  # type: ignore

        for i, (idx, row) in enumerate(self.spreadsheet_df.iterrows()):
            try:
                self.spreadsheet_df.at[idx, "id"] = int(row["id"])
            except ValueError:
                add_error(i + 1, "id", "Invalid ID", "invalid_value")
                continue
            
            if row["id"] not in self.df["id"].values:
                add_error(i + 1, "id", "Sample ID not found in the project", "invalid_value")
                continue
            
        if len(self.spreadsheet_dummy.errors) > 0:
            return False

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            self.prepare()
            return self.make_response()
        
        self.spreadsheet_df = self.spreadsheet_df.replace("", np.nan)

        for idx, row in self.spreadsheet_df.iterrows():
            sample_id = row["id"]
            for attribute_name in self.df.columns:
                if attribute_name in ["id", "name"]:
                    continue
                attribute_type = AttributeType.get_attribute_by_label(attribute_name)
                if pd.isna(val := row[attribute_name]):
                    if (attribute := db.get_sample_attribute(sample_id=row["id"], name=attribute_name)) is not None:
                        db.delete_sample_attribute(sample_id=sample_id, name=attribute_name)
                else:
                    db.set_sample_attribute(sample_id=sample_id, name=attribute_name, value=val, type=attribute_type)

        flash("Sample attributes updated", "success")
        return make_response(redirect=url_for("projects_page.project_page", project_id=self.project.id))
