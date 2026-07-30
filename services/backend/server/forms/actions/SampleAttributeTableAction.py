import pandas as pd
from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ...components.tables.spreadsheet import (
    TextColumn, IntegerColumn, DropdownColumn, InvalidCellValue,
)
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class SampleAttributeTableAction(HTMXForm):
    template_path = "forms/sample_attribute_table_form.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[],
        allow_new_cols=True,
        allow_col_rename=True,
    )

    def __init__(self, project: models.Project) -> None:
        super().__init__()
        self.project = project
        self._context["project"] = project
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", project_id=project.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            project_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SampleAttributeTableAction":
            project = session.get_one(
                Q.project.select(id=project_id),
                options=[orm.selectinload(models.Project.samples)],
            )
            form = SampleAttributeTableAction(project=project)

            # Build columns: sample_id + sample_name + attribute types + any extra columns from DB
            for col in [
                IntegerColumn("sample_id", "ID", 50, required=True, read_only=True),
                DropdownColumn("sample_name", "Sample Name", 200, required=True, choices=[s.name for s in project.samples], all_options_required=True, unique=True, read_only=True),
            ]:
                form.spreadsheet.add_column(col)

            for attribute_type in C.AttributeType.as_list()[1:]:
                form.spreadsheet.add_column(
                    TextColumn(attribute_type.label, attribute_type.display_name.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH, can_be_deleted=True)
                )

            # Get sample data from DB
            df = session.pd.get_project_samples(project.id).sort_values("sample_id").reset_index(drop=True)

            # Add any extra columns from the data that aren't predefined
            for col in df.columns:
                if col not in form.spreadsheet.columns:
                    form.spreadsheet.add_column(TextColumn(col, col.replace("_", " ").title(), 100, can_be_deleted=True))

            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                post_url=form.post_url,
                df=df,
            )

            return form
        return dependency

    @htmx_route("GET", "/{project_id}/edit-sample-attributes")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SampleAttributeTableAction" = Depends(SampleAttributeTableAction.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{project_id}/edit-sample-attributes")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SampleAttributeTableAction" = Depends(SampleAttributeTableAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> responses.Response:
            df = form.spreadsheet.data

            if "sample_id" not in df.columns:
                form.spreadsheet.add_general_error("Missing 'sample_id' column")
                form.assert_valid()

            if "sample_name" not in df.columns:
                form.spreadsheet.add_general_error("Missing 'sample_name' column")
                form.assert_valid()

            # Validate column name lengths
            _df = df.drop(columns=["sample_id", "sample_name"])
            if not _df.empty and _df.columns.str.len().min() < 3:
                shortest_col = _df.columns[_df.columns.str.len() == _df.columns.str.len().min()].values[0]
                form.spreadsheet.add_general_error(f"Column: '{shortest_col}', specify more descriptive column name by right-clicking column and 'Rename this column'")
                form.assert_valid()

            if df.columns.duplicated().any():
                form.spreadsheet.add_general_error("Duplicate column names")
                form.assert_valid()

            # Validate each row
            for idx, row in df.iterrows():
                sample = session.first(Q.sample.select(id=row["sample_id"]))
                if sample is None:
                    form.spreadsheet.add_error(idx, "sample_id", InvalidCellValue(f"Sample with ID {row['sample_id']} does not exist"))
                    continue
                if sample.project_id != form.project.id:
                    form.spreadsheet.add_error(idx, "sample_id", InvalidCellValue(f"Sample with ID {row['sample_id']} does not belong to this project"))
                    continue
                if sample.name != row["sample_name"]:
                    form.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"Sample name does not match sample with ID {row['sample_id']}"))
                    continue

            form.assert_valid()

            # Save attributes
            for _, row in df.iterrows():
                sample = session.get_one(Q.sample.select(id=row["sample_id"]))
                for attribute_name in df.columns:
                    if attribute_name in ["sample_id", "sample_name"]:
                        continue
                    attribute_type = C.AttributeType.get_attribute_by_label(attribute_name)
                    if pd.isna(row[attribute_name]):
                        existing = sample.get_attribute(attribute_name)
                        if existing is not None:
                            sample.delete_sample_attribute(attribute_name)
                    else:
                        sample.set_attribute(attribute_name, row[attribute_name], attribute_type)

            # Delete removed columns
            for label, col in form.spreadsheet.columns.items():
                if label not in df.columns and col.can_be_deleted:
                    for sample in form.project.samples:
                        sample.delete_sample_attribute(label)

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=form.project.id).include_query_params(tab="project-attributes-tab"),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route