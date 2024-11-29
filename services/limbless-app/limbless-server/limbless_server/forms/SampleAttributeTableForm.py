import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from limbless_db import models
from limbless_db.categories import AttributeType

from .. import logger, db  # noqa F401
from ..tools import SpreadSheetColumn
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput


class SampleAttributeTableForm(HTMXFlaskForm):
    _template_path = "forms/sample_attribute_table_form.html"
    _form_label = "sample_attribute_table_form"

    predefined_columns = [
        SpreadSheetColumn("id", "ID", "text", 50, str),
        SpreadSheetColumn("sample_name", "Sample Name", "text", 170, str),
    ] + [SpreadSheetColumn(t.label, t.name, "text", 100, str) for i, t in enumerate(AttributeType.as_list()[1:])]

    def __init__(self, project: models.Project, formdata: dict = {}):
        super().__init__(formdata=formdata)
        self.project = project

        self._context["project"] = project
        df = db.get_project_sample_attributes_df(self.project.id)

        columns = SampleAttributeTableForm.predefined_columns.copy()

        for col in df.columns:
            if col not in [c.label for c in columns]:
                SpreadSheetColumn(col, col.replace("_", " ").title(), "text", 100, str)

        csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=columns, csrf_token=csrf_token,
            post_url=url_for('projects_htmx.edit_sample_attributes', project_id=project.id),
            formdata=formdata, allow_new_cols=True, df=df, allow_col_rename=True
        )

    def validate(self) -> bool:
        if not super().validate() or self.formdata is None:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        
        if "id" not in df.columns:
            self.spreadsheet.add_general_error("Missing 'id' column",)
            return False
        
        if "sample_name" not in df.columns:
            self.spreadsheet.add_general_error("Missing 'sample_name' column",)
            return False

        _df = df.drop(columns=["id", "sample_name"])
        if _df.columns.str.len().min() < 3:
            shortest_col = _df.columns[_df.columns.str.len() == _df.columns.str.len().min()].values[0]
            self.spreadsheet.add_general_error(f"Column: '{shortest_col}', specify more descriptive column name by right-clicking column and 'Rename this column'",)
            return False

        if df.columns.duplicated().any():
            self.spreadsheet.add_general_error("Duplicate column names",)
            return False

        for i, (idx, row) in enumerate(df.iterrows()):
            try:
                df.at[idx, "id"] = int(row["id"])
            except ValueError:
                self.spreadsheet.add_error(i + 1, "id", "Invalid ID", "invalid_value")
                continue
            
            if row["id"] not in df["id"].values:
                self.spreadsheet.add_error(i + 1, "id", "Sample ID not found in the project", "invalid_value")
                continue
            
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        for idx, row in self.df.iterrows():
            sample_id = row["id"]
            for attribute_name in self.df.columns:
                if attribute_name in ["id", "sample_name"]:
                    continue
                attribute_type = AttributeType.get_attribute_by_label(attribute_name)
                if pd.isna(val := row[attribute_name]):
                    if (_ := db.get_sample_attribute(sample_id=row["id"], name=attribute_name)) is not None:
                        db.delete_sample_attribute(sample_id=sample_id, name=attribute_name)
                else:
                    db.set_sample_attribute(sample_id=sample_id, name=attribute_name, value=val, type=attribute_type)

        flash("Sample attributes updated", "success")
        return make_response(redirect=url_for("projects_page.project_page", project_id=self.project.id))
