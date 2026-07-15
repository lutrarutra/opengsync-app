import pandas as pd
from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, categories as C

from ....core import responses, exceptions as exc, dependencies
from ....components import inputs
from ....components.tables import TextColumn
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ....components.tables import MissingCellValue

class SampleAttributeAnnotationForm(HTMXWorkflowStep):
    workflow: LibraryAnnotationWorkflow

    template_path = "workflows/library_annotation/sas-sample_attribute_annotation.html"

    predefined_columns: list = [
        TextColumn("sample_name", "Sample Name", 200, required=True, read_only=True),
        TextColumn("sample_id", "Sample ID", 170, required=True, read_only=True),
    ] + [TextColumn(t.label, t.label.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH) for t in C.AttributeType.as_list()[1:]]

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=predefined_columns, allow_col_rename=True, allow_new_cols=True, allow_new_rows=False)

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.workflow = workflow
        sample_table = workflow.tables["sample_table"].copy()
        sample_table["sample_id"] = sample_table["sample_id"].astype(object).replace(pd.NA, "(new)")
        self.spreadsheet.configure(df=sample_table, csrf_token=self.csrf_token_value, post_url=self.post_url)

    @property
    def post_url(self) -> responses.URL:
        return SampleAttributeAnnotationForm.PostURL(
            SampleAttributeAnnotationForm.Submit, prefix="LibraryAnnotationWorkflow", seq_request_id=self.workflow.seq_request_id
        ).include_query_params(uuid=self.workflow.uuid)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> SampleAttributeAnnotationForm:
            return cls(workflow=workflow)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
            form: SampleAttributeAnnotationForm = Depends(SampleAttributeAnnotationForm.Init()),
        ) -> Response:
            # form.spreadsheet.set_data(workflow.tables["sample_table"])
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            form: "SampleAttributeAnnotationForm" = Depends(SampleAttributeAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data
            sample_table = workflow.tables["sample_table"]

            if df.columns.str.len().min() < 3:
                shortest_col = df.columns[df.columns.str.len() == df.columns.str.len().min()].values[0]
                form.spreadsheet._add_general_error(f"Column: '{shortest_col}', specify more descriptive column name by right-clicking column and 'Rename this column'",)
                raise exc.FormValidationException(form)

            missing_samples = sample_table.loc[~sample_table["sample_name"].isin(df["sample_name"]), "sample_name"].values.tolist()
            if len(missing_samples) > 0:
                form.spreadsheet.add_general_error(f"Sample(s) not found in the sample table: {', '.join(missing_samples)}")  # type: ignore

            for col in df.columns:
                if col not in form.spreadsheet.columns.keys():
                    form.spreadsheet.add_column(TextColumn(label=col, name=col.replace("_", " ").title(), width=100, max_length=models.SampleAttribute.MAX_NAME_LENGTH))

            for idx, row in df.iterrows():
                for col in df.columns:
                    if col == "sample_name":
                        continue
                    
                    if pd.isna(df[col]).all():
                        continue
                    
                    if pd.isna(row[col]):
                        form.spreadsheet._add_error(idx, col, MissingCellValue("Missing value"))

            if form.errors:
                raise exc.FormValidationException(form)

            df = df.dropna(how="all")

            for idx, row in df.iterrows():
                sample_name = row["sample_name"]
                for col in df.columns:
                    if col in ["sample_name", "sample_id"] or df[col].isna().all():
                        continue
                    sample_table.loc[sample_table["sample_name"] == sample_name, f"_attr_{col}"] = row[col]

            workflow.tables["sample_table"] = sample_table
            return workflow.get_next_step(form).make_response()
        return route




    