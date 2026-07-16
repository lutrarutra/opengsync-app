import pandas as pd
from loguru import logger
from fastapi import Depends, Response

from opengsync_db import categories as C, models

from ....core import responses, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn, DuplicateCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep

class FlexAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-flex_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Multiplexing Pool", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Barcode ID", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH),
    ])

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return (
            C.SubmissionType.get(workflow.header["submission_type_id"]) in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and
            C.LibraryType.TENX_SC_GEX_FLEX.id in workflow.tables["library_table"]["library_type_id"].values
        )

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.flex_table = workflow.tables["sample_pooling_table"][["sample_name", "sample_pool"]].drop_duplicates()
        self.sample_table = self.flex_table.copy()
        self.spreadsheet.set_data(self.flex_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: FlexAnnotationForm = Depends(FlexAnnotationForm.PreviousStep()),
        ) -> Response:
            mux_table = form.workflow.tables["sample_pooling_table"][["sample_name", "sample_pool", "mux_barcode"]].drop_duplicates(["sample_name", "sample_pool"])
            mux_table["barcode_id"] = mux_table["mux_barcode"].str.replace("AB", "BC").values
            form.spreadsheet.set_data(mux_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: FlexAnnotationForm = Depends(FlexAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data

            duplicated = df.duplicated(subset=["sample_pool", "barcode_id"] if "sample_pool" in df.columns else ["barcode_id"], keep=False) & pd.notna(df["barcode_id"])        
            for idx, _ in df.iterrows():
                if duplicated.at[idx]:
                    form.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("Duplicate 'Barcode ID' in the same 'Sample Pool' is not allowed."))
                    
            form.assert_valid()
            
            sample_pooling_table = form.workflow.tables["sample_pooling_table"]
        
            if form.flex_table is None:
                logger.error(f"{form.workflow.uuid}: Flex table is None.")
                raise Exception("Flex table is None.")
            
            sample_pooling_table["mux_barcode"] = parsing.map_columns(sample_pooling_table, df, idx_columns=["sample_name", "sample_pool"], col="barcode_id")

            library_table = form.workflow.tables["library_table"]
            abc_libraries = library_table.loc[library_table["library_type_id"] == C.LibraryType.TENX_SC_ABC_FLEX.id, "library_name"].values.tolist()
            sample_pooling_table.loc[sample_pooling_table["library_name"].isin(abc_libraries), "mux_barcode"] = sample_pooling_table.loc[sample_pooling_table["library_name"].isin(abc_libraries), "mux_barcode"].str.replace("BC", "AB")
            form.workflow.tables["sample_pooling_table"] = sample_pooling_table

            library_table_data = {
                "library_name": [],
                "sample_name": [],
                "library_type": [],
                "library_type_id": [],
            }

            def add_library(sample_pool: str, library_type: C.LibraryType):
                library_table_data["library_name"].append(f"{sample_pool}_{library_type.identifier}")
                library_table_data["sample_name"].append(sample_pool)
                library_table_data["library_type"].append(library_type.name)
                library_table_data["library_type_id"].append(library_type.id)

            for (sample_pool,), _ in sample_pooling_table.groupby(["sample_pool"], sort=False):
                add_library(sample_pool, C.LibraryType.TENX_SC_GEX_FLEX)  # type: ignore

                if form.workflow.metadata["antibody_capture"]:
                    add_library(sample_pool, C.LibraryType.TENX_SC_ABC_FLEX)  # type: ignore

            library_table = pd.DataFrame(library_table_data)
            form.workflow.tables["library_table"] = library_table
            return form.workflow.get_next_step(form).make_response()
        return route

