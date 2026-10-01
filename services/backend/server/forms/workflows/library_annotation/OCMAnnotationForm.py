import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C, models

from ....core import responses, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn, DuplicateCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep

class OCMAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-ocm_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Multiplexing Pool", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Barcode ID", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=lambda x: str(x).strip().upper()),
    ])

    allowed_barcodes = [f"OB{i}" for i in range(1, 5)]

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return (
            workflow.header["submission_type_id"] in [C.SubmissionType.POOLED_LIBRARIES.id, C.SubmissionType.UNPOOLED_LIBRARIES.id] and
            (workflow.metadata["mux_type_id"] == C.MUXType.TENX_ON_CHIP.id)
        )

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.sample_pooling_table = workflow.tables["sample_pooling_table"]
        # One row per sample in each pool, not per sample x library type
        self.spreadsheet.set_data(self.sample_pooling_table.drop_duplicates(subset=["sample_name", "sample_pool"]))


    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: OCMAnnotationForm = Depends(OCMAnnotationForm.Init()),
        ) -> Response:
            df = form.workflow.tables["sample_pooling_table"].drop_duplicates(subset=["sample_name", "sample_pool"])
            df["barcode_id"] = df["mux_barcode"]
            form.spreadsheet.set_data(df)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: OCMAnnotationForm = Depends(OCMAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data

            def padded_barcode_id(s: str) -> str:
                number = ''.join(filter(str.isdigit, s))
                return f"OB{number}"
            
            df["barcode_id"] = df["barcode_id"].apply(lambda s: padded_barcode_id(s) if pd.notna(s) else None)
            duplicate_annotation = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)

            for i, (idx, row) in enumerate(df.iterrows()):
                if duplicate_annotation[i]:
                    form.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("Duplicate 'Barcode ID' in the same 'Sample Pool' is not allowed."))
                    continue
                
                if row["barcode_id"] not in OCMAnnotationForm.allowed_barcodes:
                    form.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"Barcode ID must be one of {OCMAnnotationForm.allowed_barcodes}."))

            form.assert_valid()
            
            form.sample_pooling_table["mux_barcode"] = parsing.map_columns(form.sample_pooling_table, df, idx_columns=["sample_name", "sample_pool"], col="barcode_id")
            form.workflow.tables["sample_pooling_table"] = form.sample_pooling_table

            # library_table from the previous step already has one library per pool and type (legacy
            # rebuilt it here from the service's library types and discarded it; for CUSTOM that is empty)
            return form.workflow.get_next_step(form).make_response()
        return route

