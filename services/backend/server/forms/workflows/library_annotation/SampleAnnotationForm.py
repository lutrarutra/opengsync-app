import pandas as pd
from fastapi import Request, Depends, Response, Query
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import responses, exceptions as exc, dependencies
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown
from ..HTMXWorkflowStep import HTMXWorkflowStep
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


class SampleAnnotationForm(HTMXWorkflowStep):
    _step_name = "sample_annotation"

    template_path = "workflows/library_annotation/sas-sample_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=lambda x: utils.parsing.make_alpha_numeric(x, keep=["_", "."]), validation_fnc=lambda x: utils.parsing.check_string(x, allowed_special_characters=["_"]), unique=True),
        CategoricalDropDown("genome_id", "Genome", 300, categories=dict(C.GenomeRef.as_selectable()), required=True),
    ])

    def __init__(
        self,
        request: Request,
        workflow: LibraryAnnotationWorkflow,
    ) -> None:
        super().__init__(request)
        self.workflow = workflow
        self.post_url = responses.url_for("library_annotation_workflow_sample_annotation", seq_request_id=self.seq_request.id).include_query_params(uuid=self.workflow.uuid)
        self.spreadsheet.configure(pd.DataFrame(), csrf_token=self.csrf_token_value, post_url=self.post_url)

    def begin(self, request: Request, workflow: LibraryAnnotationWorkflow) -> Response:
        form = SampleAnnotationForm(request=request, workflow=workflow)
        return form.make_response()

    @classmethod
    def Submit(
        cls,
        request: Request,
        seq_request_id: int,
        session: SyncSession,
        workflow: LibraryAnnotationWorkflow,
    ) -> Response:
        seq_request = session.get_one(Q.seq_request.select(id=seq_request_id).options(
            orm.joinedload(models.SeqRequest.requestor),
        ))
        form = SampleAnnotationForm(request=request, workflow=workflow)
        form.validate()
        workflow.tables["sample_table"] = form.spreadsheet.data
        next_form = workflow.get_next_step()
        return next_form.begin(request=request, workflow=workflow)


        


