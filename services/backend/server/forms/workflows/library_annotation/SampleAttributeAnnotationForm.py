from typing import cast

import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C

from ....core import exceptions as exc
from ....components import inputs
from ....components.tables import TextColumn, DBObjectColumn, StaticSpreadsheet
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep
from ...HTMXForm import RouteFunc, htmx_route
from ....components.tables import MissingCellValue

SAMPLE_COLUMNS = ("sample_id", "sample_name")


class SampleAttributeAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow

    template_path = "workflows/library_annotation/sas-sample_attribute_annotation.html"

    predefined_columns: list = [
        # Samples of the previous step, existing ones by "name [id]", new ones by "name [new]"
        DBObjectColumn(("sample_id", "sample_name"), "Sample", 300, categories={}, required=True, unique=True, read_only=True),
    ] + [TextColumn(t.label, t.label.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH) for t in C.AttributeType.as_list()[1:]]

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=predefined_columns, allow_col_rename=True, allow_new_cols=True, allow_new_rows=False)

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.workflow = workflow
        sample_table = workflow.tables["sample_table"].copy()
        existing = sample_table.dropna(subset=["sample_id"])
        cast(DBObjectColumn, self.spreadsheet.columns["Sample"]).set_categories(
            {
                int(sample_id): f"{sample_name} [{int(sample_id)}]"
                for sample_id, sample_name in zip(existing["sample_id"], existing["sample_name"])
            },
            new_names=sample_table.loc[sample_table["sample_id"].isna(), "sample_name"].tolist(),
        )
        # Attributes of existing samples (incl. custom ones) get their own columns
        for col in sample_table.columns:
            if col.startswith("_attr_") and (label := col.removeprefix("_attr_")) not in self.spreadsheet.columns.keys():
                self.spreadsheet.add_column(column=TextColumn(
                    label=label, name=label.replace("_", " ").title(),
                    width=100, max_length=models.SampleAttribute.MAX_NAME_LENGTH,
                ))
        sample_table.columns = sample_table.columns.str.removeprefix("_attr_")
        self.spreadsheet.configure(df=sample_table, csrf_token=self.csrf_token_value, post_url=self.post_url)

    def prepare_context(self) -> None:
        # A used column is filled for every sample, "Treatment" is a custom column
        self._context["example_spreadsheet"] = StaticSpreadsheet(
            pd.DataFrame({
                "sample": ["liver_ctrl_1 [12]", "liver_ctrl_2 [13]", "liver_treated_1 [new]", "organoid_day_7 [new]"],
                "sex": ["female", "male", "female", "male"],
                "age": ["52", "47", "61", "34"],
                "tissue": ["liver", "liver", "liver", "intestine"],
                "condition": ["control", "control", "treated", "day 7"],
                "treatment": ["none", "none", "drug_a 10uM", "none"],
            }),
            columns=[
                TextColumn("sample", "Sample", 300),
                TextColumn("sex", "Sex", 100),
                TextColumn("age", "Age", 100),
                TextColumn("tissue", "Tissue", 100),
                TextColumn("condition", "Condition", 100),
                TextColumn("treatment", "Treatment", 100),
            ],
            id="sample-attribute-annotation-example",
        )

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: SampleAttributeAnnotationForm = Depends(SampleAttributeAnnotationForm.Init()),
        ) -> Response:
            df = form.workflow.tables["sample_table"]
            for col in df.columns:
                if col.startswith("_attr_"):
                    col = col.removeprefix("_attr_")
                    if col not in form.spreadsheet.columns.keys():
                        form.spreadsheet.add_column(
                            column=TextColumn(
                                label=col, name=col.replace("_", " ").title(),
                                width=100, max_length=models.SampleAttribute.MAX_NAME_LENGTH
                            )
                        )
            df.columns = df.columns.str.removeprefix("_attr_")
            form.spreadsheet.set_data(df)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SampleAttributeAnnotationForm" = Depends(SampleAttributeAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data
            sample_table = form.workflow.tables["sample_table"]

            if df.columns.str.len().min() < 3:
                shortest_col = df.columns[df.columns.str.len() == df.columns.str.len().min()].values[0]
                form.spreadsheet.add_general_error(f"Column: '{shortest_col}', specify more descriptive column name by right-clicking column and 'Rename this column'",)
                raise exc.FormValidationException(form)

            missing_samples = sample_table.loc[~sample_table["sample_name"].isin(df["sample_name"]), "sample_name"].values.tolist()
            if len(missing_samples) > 0:
                form.spreadsheet.add_general_error(f"Sample(s) not found in the sample table: {', '.join(missing_samples)}")  # type: ignore

            for col in df.columns:
                if col not in form.spreadsheet.columns.keys() and col not in SAMPLE_COLUMNS:
                    form.spreadsheet.add_column(TextColumn(label=col, name=col.replace("_", " ").title(), width=100, max_length=models.SampleAttribute.MAX_NAME_LENGTH))

            for idx, row in df.iterrows():
                for col in df.columns:
                    if col in SAMPLE_COLUMNS:
                        continue
                    
                    if pd.isna(df[col]).all():
                        continue
                    
                    if pd.isna(row[col]):
                        form.spreadsheet.add_error(idx, col, MissingCellValue("Missing value"))

            form.assert_valid()

            df = df.dropna(how="all")

            for idx, row in df.iterrows():
                sample_name = row["sample_name"]
                for col in df.columns:
                    if col in SAMPLE_COLUMNS or df[col].isna().all():
                        continue
                    sample_table.loc[sample_table["sample_name"] == sample_name, f"_attr_{col}"] = row[col]

            form.workflow.tables["sample_table"] = sample_table
            return form.workflow.get_next_step(form).make_response()
        return route




    