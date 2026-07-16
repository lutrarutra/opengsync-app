import pandas as pd
from loguru import logger
from fastapi import Depends, Response

from opengsync_db import categories as C, models

from ....core import responses, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn, DuplicateCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep

class ParseMuxAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-parse_mux_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Multiplexing Pool", 300, required=True, read_only=True),
        TextColumn("well", "Well", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=lambda x: str(x).strip().upper()),
    ])

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return (
            C.SubmissionType.get(workflow.header["submission_type_id"]) in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and
            (workflow.metadata["mux_type_id"] == C.MUXType.PARSE_WELLS.id)
        )

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.sample_pooling_table = workflow.tables["sample_pooling_table"]
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.spreadsheet.set_data(self.sample_pooling_table.drop_duplicates(subset=["sample_name", "sample_pool"]))


    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: ParseMuxAnnotationForm = Depends(ParseMuxAnnotationForm.Init()),
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> Response:
            df = workflow.tables["sample_pooling_table"]
            df["well"] = df["mux_well"]
            form.spreadsheet.set_data(df.drop_duplicates(subset=["sample_name", "sample_pool"]))
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: ParseMuxAnnotationForm = Depends(ParseMuxAnnotationForm.Validate()),
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> Response:
            df = form.spreadsheet.data
            duplicate_annotation = df.duplicated(subset=["sample_pool", "well"], keep=False)
            for idx, _ in df.iterrows():
                if duplicate_annotation.at[idx]:
                    form.spreadsheet.add_error(idx, "well", DuplicateCellValue("Duplicate 'Well' in the same 'Sample Pool' is not allowed."))
                    continue

            form.assert_valid()
            
            
            form.sample_pooling_table["mux_barcode"] = parsing.map_columns(form.sample_pooling_table, df, idx_columns=["sample_name", "sample_pool"], col="well")
            workflow.tables["sample_pooling_table"] = form.sample_pooling_table

            library_table_data = {
                "library_name": [],
                "sample_name": [],
                "library_type": [],
                "library_type_id": [],
            }

            service_type_enum = C.ServiceType.get(workflow.metadata["service_type_id"])

            def add_library(sample_pool: str, library_type: C.LibraryType):
                library_table_data["library_name"].append(f"{sample_pool}_{library_type.identifier}")
                library_table_data["sample_name"].append(sample_pool)
                library_table_data["library_type"].append(library_type.name)
                library_table_data["library_type_id"].append(library_type.id)

            for (sample_pool,), _ in form.sample_pooling_table.groupby(["sample_pool"], sort=False):
                for library_type in service_type_enum.library_types:
                    add_library(sample_pool, library_type)  # type: ignore

                if workflow.metadata["antibody_capture"]:
                    if service_type_enum in C.ServiceType.get_flex_services():
                        add_library(sample_pool, C.LibraryType.TENX_SC_ABC_FLEX)  # type: ignore
                    else:
                        add_library(sample_pool, C.LibraryType.TENX_ANTIBODY_CAPTURE)  # type: ignore

                if workflow.metadata["vdj_b"]:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_B)  # type: ignore

                if workflow.metadata["vdj_t"]:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_T)  # type: ignore

                if workflow.metadata["vdj_t_gd"]:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_T_GD)  # type: ignore

                if workflow.metadata["crispr_screening"]:
                    add_library(sample_pool, C.LibraryType.TENX_CRISPR_SCREENING)  # type: ignore

                if workflow.metadata.get("parse_crispr", False):
                    add_library(sample_pool, C.LibraryType.PARSE_SC_CRISPR)  # type: ignore
                
                if workflow.metadata.get("parse_tcr", False):
                    add_library(sample_pool, C.LibraryType.PARSE_EVERCODE_TCR)  # type: ignore

                if workflow.metadata.get("parse_bcr", False):
                    add_library(sample_pool, C.LibraryType.PARSE_EVERCODE_BCR)  # type: ignore
            
            workflow.tables["library_table"] = pd.DataFrame(library_table_data)
            return workflow.get_next_step(form).make_response()
        return route

