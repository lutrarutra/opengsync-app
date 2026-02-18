import os

import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import AttributeType

from .... import logger, db
from ....core import runtime
from ....tools.spread_sheet_components import TextColumn, MissingCellValue, SpreadSheetColumn
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from ...SpreadsheetInput import SpreadsheetInput


class SampleAttributeAnnotationForm(LibraryAnnotationWorkflow):
    _template_path = "workflows/library_annotation/sas-sample_attribute_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "sample_attribute_annotation"

    predefined_columns = [
        TextColumn("sample_name", "Sample Name", 200, required=True, read_only=True),
        TextColumn("sample_id", "Sample ID", 170, required=True, read_only=True),
    ] + [TextColumn(t.label, t.label.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH) for t in AttributeType.as_list()[1:]]

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        LibraryAnnotationWorkflow.__init__(self, seq_request=seq_request, step_name=SampleAttributeAnnotationForm._step_name, formdata=formdata, uuid=uuid)
        self.upload_path = os.path.join(runtime.app.uploads_folder.as_posix(), "seq_request")
        self.columns: list[SpreadSheetColumn] = SampleAttributeAnnotationForm.predefined_columns.copy()  # type: ignore

        sample_table = self.tables["sample_table"]
        df = sample_table[["sample_name", "sample_id"]].copy()
        df["sample_id"] = df["sample_id"].astype(pd.StringDtype())
        df.loc[df["sample_id"].isna(), "sample_id"] = "new"
    
        for col in SampleAttributeAnnotationForm.predefined_columns:
            if col.label in df.columns:
                continue
            
            df[col.label] = ""

        for _, row in sample_table[sample_table["sample_id"].notna()].iterrows():
            if (sample := db.samples.get(sample_id=int(row["sample_id"]))) is None:
                logger.warning(f"Sample with ID {row['sample_id']} not found in the database.")
                raise ValueError(f"Sample with ID {row['sample_id']} not found in the database.")
            
            for attr in sample.attributes:
                df.loc[df["sample_name"] == row["sample_name"], attr.name] = attr.value

        for col in df.columns:
            if col not in [c.label for c in self.columns]:
                self.columns.append(TextColumn(col, col.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH))

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_sas_form', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_cols=True, allow_col_rename=True, df=df
        )

    def fill_previous_form(self):
        df = self.tables["sample_table"]
        df.loc[df["sample_id"].isna(), "sample_id"] = "new"
        for col in df.columns:
            if col.startswith("_attr_"):
                col = col.removeprefix("_attr_")
                if col not in self.spreadsheet.columns.keys():
                    self.spreadsheet.add_column(
                        label=col, column=TextColumn(
                            label=col, name=col.replace("_", " ").title(),
                            width=100, max_length=models.SampleAttribute.MAX_NAME_LENGTH
                        )
                    )
        df.columns = df.columns.str.removeprefix("_attr_")
        self.spreadsheet.set_data(df)

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
                self.spreadsheet.add_column(label=col, column=TextColumn(label=col, name=col.replace("_", " ").title(), width=100, max_length=models.SampleAttribute.MAX_NAME_LENGTH))

        for idx, row in df.iterrows():
            for col in df.columns:
                if col == "sample_name":
                    continue
                
                if pd.isna(df[col]).all():
                    continue
                
                if pd.isna(row[col]):
                    self.spreadsheet.add_error(idx, col, MissingCellValue("Missing value"))
                    validated = False

        if not validated or len(self.spreadsheet._errors) > 0:
            return False

        self.df = df.dropna(how="all")
        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        for idx, row in self.df.iterrows():
            sample_name = row["sample_name"]
            for col in self.df.columns:
                if col in ["sample_name", "sample_id"] or self.df[col].isna().all():
                    continue
                self.sample_table.loc[self.sample_table["sample_name"] == sample_name, f"_attr_{col}"] = row[col]

        self.tables["sample_table"] = self.sample_table
        return self.get_next_step().make_response()