import pandas as pd
from fastapi import Request, Depends, Response, Query
from sqlalchemy import orm

from opengsync_db import models, queries as Q, AsyncSession, categories as C

from ....core import responses, exceptions as exc, dependencies
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow

class SampleAnnotationForm(LibraryAnnotationWorkflow):
    _step_name = "sample_annotation"

    template_path = "workflows/library_annotation/sas-sample_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=lambda x: utils.parsing.make_alpha_numeric(x, keep=["_", "."]), validation_fnc=lambda x: utils.parsing.check_string(x, allowed_special_characters=["_"]), unique=True),
        CategoricalDropDown("genome_id", "Genome", 300, categories=dict(C.GenomeRef.as_selectable()), required=True),
    ])

    def __init__(
        self,
        request: Request,
        seq_request: models.SeqRequest,
        uuid: str | None = None,
    ) -> None:
        super().__init__(
            seq_request=seq_request,
            request=request,
            uuid=uuid,
            step_name=self._step_name,
        )
        self.seq_request = seq_request
        self.post_url = responses.url_for("library_annotation_workflow_sample_annotation", seq_request_id=self.seq_request.id).include_query_params(uuid=self.uuid)
        self.spreadsheet.configure(pd.DataFrame(), csrf_token=self.csrf_token_value, post_url=self.post_url)

    async def begin(self, previous_form: LibraryAnnotationWorkflow) -> Response:
        form = SampleAnnotationForm(seq_request=previous_form.seq_request, request=previous_form.request, uuid=previous_form.uuid)
        await form._init_msf_state()
        return await form.make_response()

    @staticmethod
    async def process_request(
        request: Request,
        seq_request_id: int,
        uuid: str = Query(..., description="The UUID of the workflow state."),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id).options(
            orm.joinedload(models.SeqRequest.requestor),
        ))
        form = SampleAnnotationForm(request=request, seq_request=seq_request, uuid=uuid)
        await form._init_msf_state()
        form.tables["sample_table"] = form.spreadsheet.data
        next_form = await form.get_next_step()
        return await next_form.begin(previous_form=form)


        


