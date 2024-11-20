import os
import string
from typing import Optional

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType, AttributeType

from .... import logger, db  # noqa F401
from ....tools import SpreadSheetColumn
from ...MultiStepForm import MultiStepForm
from .CompleteSASForm import CompleteSASForm
from ...SpreadsheetInput import SpreadsheetInput


class SampleAttributeAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-11.html"
    _workflow_name = "library_annotation"
    _step_name = "sample_attribute_annotation"

    predefined_columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str)
    } | dict([(t.label, SpreadSheetColumn(string.ascii_uppercase[i + 1], t.label, t.name, "text", 100, str)) for i, t in enumerate(AttributeType.as_list()[1:])])

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=SampleAttributeAnnotationForm._workflow_name,
            step_name=SampleAttributeAnnotationForm._step_name, previous_form=previous_form, step_args={}
        )

        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.upload_path = os.path.join("uploads", "seq_request")

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        library_table = self.tables["library_table"]
        sample_table = self.tables["sample_table"]

        library_table["is_cmo_sample"] = False
        library_table["is_flex_sample"] = False
        for sample_name, _df in library_table.groupby("sample_name"):
            if LibraryType.TENX_MULTIPLEXING_CAPTURE.id in _df["library_type_id"].unique():
                library_table.loc[library_table["sample_name"] == sample_name, "is_cmo_sample"] = True
            if LibraryType.TENX_SC_GEX_FLEX.id in _df["library_type_id"].unique():
                library_table.loc[library_table["sample_name"] == sample_name, "is_flex_sample"] = True

        self.update_table("library_table", library_table, False)

        df = sample_table[["sample_name"]].copy()
    
        for col in SampleAttributeAnnotationForm.predefined_columns.values():
            if col.label in df.columns:
                continue
            
            df[col.label] = ""

        for _, row in sample_table[sample_table["sample_id"].notna()].iterrows():
            attributes = db.get_sample_attributes(sample_id=int(row["sample_id"]))
            for attr in attributes:
                df.loc[df["sample_name"] == row["sample_name"], attr.name] = attr.value

        columns = SampleAttributeAnnotationForm.predefined_columns.copy()
        for col in df.columns:
            if col not in columns.keys():
                columns[col] = SpreadSheetColumn(string.ascii_uppercase[len(columns)], col, col.replace("_", " ").title(), "text", 100, str)

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_sas_form', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_cols=True, allow_col_rename=True, df=df
        )

    def validate(self) -> bool:
        validated = super().validate()
                
        if not validated:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.sample_table = self.tables["sample_table"]
        df = self.spreadsheet.df

        if df.columns.str.len().min() < 3:
            shortest_col = df.columns[df.columns.str.len() == df.columns.str.len().min()].values[0]
            self.spreadsheet.add_general_error(f"Column: '{shortest_col}', specify more descriptive column name by right-clicking column and 'Rename this column'",)
            return False

        missing_samples = self.sample_table.loc[~self.sample_table["sample_name"].isin(df["sample_name"]), "sample_name"].values.tolist()
        if len(missing_samples) > 0:
            self.spreadsheet.add_general_error(f"Sample(s) not found in the sample table: {', '.join(missing_samples)}")
            validated = False

        for col in df.columns:
            if col not in self.spreadsheet.columns.keys():
                self.spreadsheet.add_column(label=col, name=col.replace("_", " ").title(), type="text", width=100, var_type=str, clean_up_fnc=lambda x: x.strip())

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]) or row["sample_name"] == "":
                self.spreadsheet.add_error(i + 1, "sample_name", "Missing value", "missing_value")
                validated = False
                continue
            
            if row["sample_name"] not in self.tables["sample_table"]["sample_name"].values:
                self.spreadsheet.add_error(i + 1, "sample_name", f"Unknown sample name '{row['sample_name']}'", "invalid_value")
                validated = False
                continue
            
            for col in df.keys():
                if col == "sample_name":
                    continue
                
                if pd.isna(df[col]).all():
                    continue
                
                if pd.isna(row[col]):
                    self.spreadsheet.add_error(i + 1, col, "Missing value", "missing_value")
                    validated = False

        if len(self.spreadsheet._errors) > 0 or not validated:
            return False

        self.df = df.dropna(how="all")

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        for idx, row in self.df.iterrows():
            sample_name = row["sample_name"]
            for col in self.df.columns:
                if col == "sample_name" or self.df[col].isna().all():
                    continue
                self.sample_table.loc[self.sample_table["sample_name"] == sample_name, f"_attr_{col}"] = row[col]

        self.update_table("sample_table", self.sample_table)
        
        complete_sas_form = CompleteSASForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response()