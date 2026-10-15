from typing import Callable, Sequence, cast

import pandas as pd
from fastapi import Depends, Response
from pydantic import BaseModel

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ....core import dependencies, responses
from ....core.context import ctx
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown, QueryColumn, StaticSpreadsheet, InvalidCellValue, DuplicateCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep


def _sample_names(project_id: int | None) -> Callable[[Sequence[int]], dict[int, str]]:
    """Names of the given samples that can be reused: the samples of the project that are not rejected."""
    def lookup(ids: Sequence[int]) -> dict[int, str]:
        if project_id is None:
            return {}
        stmt = Q.sample.select(project_id=project_id).where(
            models.Sample.id.in_(ids), models.Sample.status.is_distinct_from(C.SampleStatus.REJECTED),
        )
        return {sample.id: sample.name for sample in ctx.session.get_all(stmt, limit=None)}
    return lookup


class SampleAnnotationForm(LibraryAnnotationWorkflowStep):
    template_path = "workflows/library_annotation/sas-sample_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        # A sample of the selected project, or the name of a new sample
        QueryColumn(
            "sample_id", "Sample Name", 300, required=True, unique=True, url=None, lookup=_sample_names(None), allow_new=True,
            name_column=TextColumn(
                "sample_name", "Sample Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4,
                clean_up_fnc=lambda x: utils.parsing.make_alpha_numeric(x, keep=["_", "."]),
                validation_fnc=lambda x: utils.parsing.check_string(x, allowed_special_characters=["_"]),
            ),
        ),
        # Shown as organism, the genome reference is picked by the organism of the sample
        CategoricalDropDown("genome_id", "Organism", 300, categories=dict(C.GenomeRef.as_selectable()), required=True),
    ])

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        # Without a project (a new one) every sample is new
        project_id = workflow.metadata.get("project_id")
        sample_column = cast(QueryColumn, self.spreadsheet.columns["sample_id"])
        sample_column.lookup = _sample_names(project_id)
        if project_id is not None:
            sample_column.set_url(lambda: responses.url_for("query_samples").include_query_params(project_id=project_id))
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)

    def prepare_context(self) -> None:
        self._context["example_spreadsheet"] = StaticSpreadsheet(
            pd.DataFrame({
                "sample_name": ["liver_ctrl_1", "liver_ctrl_2", "liver_treated_1", "organoid_day_7"],
                "organism": [C.GenomeRef.HUMAN.display_name] * 3 + [C.GenomeRef.MOUSE.display_name],
            }),
            columns=[TextColumn("sample_name", "Sample Name", 300), TextColumn("organism", "Organism", 300)],
            id="sample-annotation-example",
        )

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: SampleAnnotationForm = Depends(SampleAnnotationForm.Init()),
        ) -> Response:
            form.spreadsheet.set_data(form.workflow.tables["sample_table"])
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SampleAnnotationForm" = Depends(SampleAnnotationForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data

            class RowSchema(BaseModel):
                sample_id: int | None
                sample_name: str


            # Existing samples keep their id and bring their attributes along (shown in the next step)
            if (project_id := form.workflow.metadata.get("project_id")) is not None:
                for idx, row in utils.parsing.safe_iter(df, RowSchema):
                    if row.sample_id is not None:
                        sample = session.get_one(Q.sample.select(id=row.sample_id))
                    # New names that are names of project samples, e.g. pasted when the editor could not look them up
                    elif (sample := session.first(Q.sample.select(name=row.sample_name, project_id=project_id))) is None:
                        continue
                    elif sample.status == C.SampleStatus.REJECTED:
                        form.spreadsheet.add_error(idx, "sample_id", InvalidCellValue(f"Sample '{row.sample_name}' is rejected, please specify another name."))
                        continue
                    elif (df["sample_id"] == sample.id).any():
                        form.spreadsheet.add_error(idx, "sample_id", DuplicateCellValue(f"Sample '{row.sample_name}' appears multiple times."))
                        continue
                    df.loc[idx, "sample_id"] = sample.id
                    for attr in sample.attributes:
                        df.loc[idx, f"_attr_{attr.name}"] = attr.value

                form.assert_valid()

            form.workflow.tables["sample_table"] = df
            next_form = form.workflow.get_next_step(form)
            return next_form.make_response()
        return route