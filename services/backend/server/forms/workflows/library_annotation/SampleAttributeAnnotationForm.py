import pandas as pd
from fastapi import Request, Depends, Response, Query
from sqlalchemy import orm
from loguru import logger

from opengsync_db import models, queries as Q, AsyncSession, categories as C

from ....core import responses, exceptions as exc, dependencies
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow

class SampleAttributeAnnotationForm(LibraryAnnotationWorkflow):
    _step_name = "sample_attribute_annotation"
    template_path = "workflows/library_annotation/sas-sample_attribute_annotation.html"

    predefined_columns: list = [
        TextColumn("sample_name", "Sample Name", 200, required=True, read_only=True),
        TextColumn("sample_id", "Sample ID", 170, required=True, read_only=True),
    ] + [TextColumn(t.label, t.label.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH) for t in C.AttributeType.as_list()[1:]]

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=predefined_columns, allow_col_rename=True)

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
        self.post_url = responses.url_for("library_annotation_workflow_sample_attribute_annotation", seq_request_id=self.seq_request.id).include_query_params(uuid=self.uuid)
        self.spreadsheet.configure(df=pd.DataFrame(), csrf_token=self.csrf_token_value, post_url=self.post_url)

    async def begin(self):
        sample_table = await self.tables["sample_table"]
        df = sample_table[["sample_name", "sample_id"]].copy()
        df["sample_id"] = df["sample_id"].astype(pd.StringDtype())
        df.loc[df["sample_id"].isna(), "sample_id"] = "new"

        for col in SampleAttributeAnnotationForm.predefined_columns:
            if col.label in df.columns:
                continue
            
            df[col.label] = ""

        for _, row in sample_table[sample_table["sample_id"].notna()].iterrows():
            sample = await session.get_one(Q.sample.select(id=int(row["sample_id"])))
            
            for attr in sample.attributes:
                df.loc[df["sample_name"] == row["sample_name"], attr.name] = attr.value

        for col in df.columns:
            if col not in [c.label for c in self.spreadsheet.columns.values()]:
                self.spreadsheet.add_column(TextColumn(col, col.replace("_", " ").title(), 100, max_length=models.SampleAttribute.MAX_NAME_LENGTH))




    