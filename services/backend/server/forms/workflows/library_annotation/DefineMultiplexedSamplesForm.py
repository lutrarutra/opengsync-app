import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C, SyncSession

from ....core import dependencies
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, DropdownColumn, DuplicateCellValue, MissingCellValue, InvalidCellValue
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep
from .CustomAssayAnnotationForm import CustomAssayAnnotationForm

class DefineMultiplexedSamplesForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-define_mux_samples.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        DropdownColumn("sample_name", "Sample Name", 300, required=True, choices=[], read_only=False),
        TextColumn("pool", "Multiplexing Pool", 300, max_length=models.Library.name.type.length, min_length=1, validation_fnc=utils.parsing.check_string),
    ])

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.service_type = C.ServiceType.get(int(workflow.metadata["service_type_id"]))
        self.mux_type = C.MUXType.get(workflow.metadata["mux_type_id"])
        self.antibody_capture = workflow.metadata["antibody_capture"]
        self.vdj_b = workflow.metadata["vdj_b"]
        self.vdj_t = workflow.metadata["vdj_t"]
        self.vdj_t_gd = workflow.metadata["vdj_t_gd"]
        self.crispr_screening = workflow.metadata["crispr_screening"]
        self.parse_tcr = workflow.metadata.get("parse_tcr", False)
        self.parse_bcr = workflow.metadata.get("parse_bcr", False)
        self.parse_crispr = workflow.metadata.get("parse_crispr", False)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        return workflow.metadata["mux_type_id"] is not None

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
        ) -> Response:
            form = DefineMultiplexedSamplesForm(workflow)
            sample_pooling_table = workflow.tables["sample_pooling_table"].rename(
                columns={"sample_pool": "pool"}
            )
            sample_pooling_table = sample_pooling_table.drop_duplicates(subset=["sample_name", "pool"])
            form.spreadsheet.set_data(sample_pooling_table)
            return form.make_response()
        return route


    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            form: "DefineMultiplexedSamplesForm" = Depends(DefineMultiplexedSamplesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data
            seq_request_samples = session.pd.get_seq_request_samples(workflow.seq_request_id)

            selected_library_types = [t.abbreviation for t in form.service_type.library_types]
            if form.antibody_capture:
                if form.service_type in C.ServiceType.get_flex_services():
                    selected_library_types.append(C.LibraryType.TENX_SC_ABC_FLEX.abbreviation)
                else:
                    selected_library_types.append(C.LibraryType.TENX_ANTIBODY_CAPTURE.abbreviation)
            if form.vdj_b:
                selected_library_types.append(C.LibraryType.TENX_VDJ_B.abbreviation)
            if form.vdj_t:
                selected_library_types.append(C.LibraryType.TENX_VDJ_T.abbreviation)
            if form.vdj_t_gd:
                selected_library_types.append(C.LibraryType.TENX_VDJ_T_GD.abbreviation)
            if form.crispr_screening:
                selected_library_types.append(C.LibraryType.TENX_CRISPR_SCREENING.abbreviation)
            if form.mux_type == C.MUXType.TENX_OLIGO:
                selected_library_types.append(C.LibraryType.TENX_MUX_OLIGO.abbreviation)
            
            if df["pool"].isna().all():
                for i, (idx, row) in enumerate(df.iterrows()):
                    if form.service_type == C.ServiceType.TENX_SC_4_PLEX_FLEX:
                        df.at[idx, "pool"] = f"flex_pool_{i // 4 + 1}"  # type: ignore
                    elif form.service_type == C.ServiceType.TENX_SC_16_PLEX_FLEX:
                        df.at[idx, "pool"] = f"flex_pool_{i // 16 + 1}"  # type: ignore
                    elif form.service_type == C.ServiceType.TENX_SC_FLEX_V2:
                        df.at[idx, "pool"] = f"flex_pool_{i // 384 + 1}"  # type: ignore
                    else:
                        df.at[idx, "pool"] = f"hto_pool_{i + 1}"  # type: ignore

            duplicate_definition = df.duplicated(subset=["sample_name", "pool"], keep=False)

            for idx, row in df.iterrows():
                if duplicate_definition.at[idx]:
                    form.spreadsheet.add_error(idx, "pool", DuplicateCellValue(f"Sample '{row['sample_name']}' is assigned to pool '{row['pool']}' multiple times."))

                duplicate_library = (seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.abbreviation).isin(selected_library_types))
                if (duplicate_library).any():
                    library_type = seq_request_samples.loc[duplicate_library, "library_type"].iloc[0]  # type: ignore
                    form.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue(f"You already have '{library_type.abbreviation}'-library from sample {row['sample_name']} in the request"))

                if not df["pool"].isna().all():
                    if pd.isna(row["pool"]):
                        form.spreadsheet.add_error(idx, "pool", MissingCellValue("missing 'Pool'"))

                if pd.notna(row["pool"]) and len(str(row["pool"])) < 4:
                    form.spreadsheet.add_error(idx, "pool", InvalidCellValue("Pool must be at least 4 characters long"))

            form.assert_valid()
                
            if form.service_type == C.ServiceType.CUSTOM:
                sample_pooling_table = {
                    "sample_pool": [],
                    "sample_name": [],
                }
                for (sample_name, sample_pool), _ in df.groupby(["sample_name", "pool"], sort=False):  # type: ignore
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    sample_pooling_table["sample_name"].append(sample_name)
                    
                sample_pooling_table = pd.DataFrame(sample_pooling_table)
                workflow.tables["sample_pooling_table"] = sample_pooling_table
                next_form = CustomAssayAnnotationForm(workflow)
                return next_form.make_response()

            library_table_data = {
                "library_name": [],
                "sample_name": [],
                "library_type": [],
                "library_type_id": [],
            }

            sample_pooling_table = {
                "sample_name": [],
                "library_name": [],
                "sample_pool": [],
            }

            def add_library(sample_pool: str, library_type: C.LibraryType):
                library_name = f"{sample_pool}_{library_type.identifier}"
                
                library_table_data["library_name"].append(library_name)
                library_table_data["sample_name"].append(sample_pool)
                library_table_data["library_type"].append(library_type.name)
                library_table_data["library_type_id"].append(library_type.id)

            def link_sample(sample_name: str, sample_pool: str, library_type: C.LibraryType):
                sample_pooling_table["sample_name"].append(sample_name)
                sample_pooling_table["sample_pool"].append(sample_pool)
                sample_pooling_table["library_name"].append(f"{sample_pool}_{library_type.identifier}")

            sample_pool: str
            for (sample_pool,), _df in df.groupby(["pool"], sort=False):  # type: ignore
                for library_type in form.service_type.library_types:
                    add_library(sample_pool, library_type)
                
                if form.antibody_capture:
                    if form.service_type in C.ServiceType.get_flex_services():
                        add_library(sample_pool, C.LibraryType.TENX_SC_ABC_FLEX)
                    else:
                        add_library(sample_pool, C.LibraryType.TENX_ANTIBODY_CAPTURE)

                if form.mux_type == C.MUXType.TENX_OLIGO:
                    add_library(sample_pool, C.LibraryType.TENX_MUX_OLIGO)
                if form.vdj_b:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_B)
                if form.vdj_t:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_T)
                if form.vdj_t_gd:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_T_GD)
                if form.crispr_screening:
                    add_library(sample_pool, C.LibraryType.TENX_CRISPR_SCREENING)
                if form.parse_crispr:
                    add_library(sample_pool, C.LibraryType.PARSE_SC_CRISPR)
                if form.parse_tcr:
                    add_library(sample_pool, C.LibraryType.PARSE_EVERCODE_TCR)
                if form.parse_bcr:
                    add_library(sample_pool, C.LibraryType.PARSE_EVERCODE_BCR)

                for _, row in _df.iterrows():
                    sample_name = row["sample_name"]

                    for library_type in form.service_type.library_types:
                        link_sample(sample_name, sample_pool, library_type)
                    if form.mux_type == C.MUXType.TENX_OLIGO:
                        link_sample(sample_name, sample_pool, C.LibraryType.TENX_MUX_OLIGO)
                    if form.antibody_capture:
                        if form.service_type in C.ServiceType.get_flex_services():
                            link_sample(sample_name, sample_pool, C.LibraryType.TENX_SC_ABC_FLEX)
                        else:
                            link_sample(sample_name, sample_pool, C.LibraryType.TENX_ANTIBODY_CAPTURE)
                    if form.vdj_b:
                        link_sample(sample_name, sample_pool, C.LibraryType.TENX_VDJ_B)
                    if form.vdj_t:
                        link_sample(sample_name, sample_pool, C.LibraryType.TENX_VDJ_T)
                    if form.vdj_t_gd:
                        link_sample(sample_name, sample_pool, C.LibraryType.TENX_VDJ_T_GD)
                    if form.crispr_screening:
                        link_sample(sample_name, sample_pool, C.LibraryType.TENX_CRISPR_SCREENING)
                    if form.parse_crispr:
                        link_sample(sample_name, sample_pool, C.LibraryType.PARSE_SC_CRISPR)
                    if form.parse_tcr:
                        link_sample(sample_name, sample_pool, C.LibraryType.PARSE_EVERCODE_TCR)
                    if form.parse_bcr:
                        link_sample(sample_name, sample_pool, C.LibraryType.PARSE_EVERCODE_BCR)

            library_table = pd.DataFrame(library_table_data)
            library_table["seq_depth"] = None
            library_table = library_table.reset_index(drop=True)

            sample_pooling_table = pd.DataFrame(sample_pooling_table)
            sample_pooling_table["mux_type_id"] = form.mux_type.id
            sample_pooling_table["mux_barcode"] = None

            workflow.tables["library_table"] = library_table
            workflow.tables["sample_pooling_table"] = sample_pooling_table
            return workflow.get_next_step(form).make_response()
        return route