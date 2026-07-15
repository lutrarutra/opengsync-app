import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ....core import responses, dependencies
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


class SampleAnnotationForm(HTMXWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-sample_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=lambda x: utils.parsing.make_alpha_numeric(x, keep=["_", "."]), validation_fnc=lambda x: utils.parsing.check_string(x, allowed_special_characters=["_"]), unique=True),
        CategoricalDropDown("genome_id", "Genome", 300, categories=dict(C.GenomeRef.as_selectable()), required=True),
    ])

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> SampleAnnotationForm:
            return cls(workflow=workflow)
        return dependency

    @property
    def post_url(self) -> responses.URL:
        return SampleAnnotationForm.PostURL(
            SampleAnnotationForm.Submit, prefix="LibraryAnnotationWorkflow", seq_request_id=self.workflow.seq_request_id
        ).include_query_params(uuid=self.workflow.uuid)
        
    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
            form: SampleAnnotationForm = Depends(SampleAnnotationForm.Init()),
        ) -> Response:
            form.spreadsheet.set_data(workflow.tables["sample_table"])
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            form: "SampleAnnotationForm" = Depends(SampleAnnotationForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data
            df["sample_id"] = None
            df["sample_id"] = df["sample_id"].astype(pd.Int64Dtype())

            if (project_id := workflow.metadata.get("project_id")) is not None:
                for idx, row in df.iterrows():
                    if (sample := session.first(Q.sample.select(name=row["sample_name"], project_id=project_id))) is not None:
                        df.loc[idx, "sample_id"] = sample.id

                        for attr in sample.attributes:
                            if attr.name not in df.columns:
                                df[attr.name] = None
                            df.loc[df["sample_name"] == sample.name, attr.name] = attr.value

            # for col in SampleAttributeAnnotationForm.predefined_columns:
            #     if col.label in df.columns:
            #         continue
                
            #     df[col.label] = ""

            for _, row in df[df["sample_id"].notna()].iterrows():
                sample = session.get_one(Q.sample.select(id=int(row["sample_id"])))
                
                for attr in sample.attributes:
                    df.loc[df["sample_name"] == row["sample_name"], attr.name] = attr.value

            workflow.tables["sample_table"] = df
            next_form = workflow.get_next_step(form)
            return next_form.make_response()
        return route