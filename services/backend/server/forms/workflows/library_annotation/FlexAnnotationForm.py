import re

import pandas as pd
from loguru import logger
from fastapi import Depends, Response

from opengsync_db import categories as C, models

from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn, DuplicateCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep

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

    @staticmethod
    def get_flex_libraries(library_table: pd.DataFrame) -> list[str]:
        """Names of the Flex GEX and Flex ABC libraries, i.e. the libraries that carry the probe barcodes."""
        flex_types = [C.LibraryType.TENX_SC_GEX_FLEX.id, C.LibraryType.TENX_SC_ABC_FLEX.id]
        return library_table.loc[library_table["library_type_id"].isin(flex_types), "library_name"].tolist()

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        # Flex libraries of a CUSTOM service can be single-plex: no probe barcode
        self.single_plex_allowed = workflow.metadata["service_type_id"] == C.ServiceType.CUSTOM.id
        self.spreadsheet.columns["barcode_id"].required = not self.single_plex_allowed
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        # Samples of a CUSTOM service can also have libraries of other types, which get no probe barcode
        self.flex_libraries = self.get_flex_libraries(workflow.tables["library_table"])
        sample_pooling_table = workflow.tables["sample_pooling_table"]
        self.flex_table = sample_pooling_table.loc[
            sample_pooling_table["library_name"].isin(self.flex_libraries), ["sample_name", "sample_pool"]
        ].drop_duplicates()
        self.sample_table = self.flex_table.copy()
        self.spreadsheet.set_data(self.flex_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: FlexAnnotationForm = Depends(FlexAnnotationForm.Init()),
        ) -> Response:
            sample_pooling_table = form.workflow.tables["sample_pooling_table"]
            library_table = form.workflow.tables["library_table"]
            gex_libraries = library_table.loc[library_table["library_type_id"] == C.LibraryType.TENX_SC_GEX_FLEX.id, "library_name"].values.tolist()
            gex_rows = sample_pooling_table[sample_pooling_table["library_name"].isin(gex_libraries)]
            mux_table = gex_rows[["sample_name", "sample_pool", "mux_barcode"]].drop_duplicates(["sample_name", "sample_pool"])
            mux_table["barcode_id"] = mux_table["mux_barcode"].values
            form.spreadsheet.set_data(mux_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: FlexAnnotationForm = Depends(FlexAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data

            # Normalise BC-style 'bc1' / '1' / 'BC01' to 'BC001' and check the barcode exists for the selected Flex kit.
            # Other barcodes (e.g. Flex v2 'A-F01') are taken as-is. Multiple barcodes per sample are separated by ';'.
            max_barcode = {
                C.ServiceType.TENX_SC_4_PLEX_FLEX.id: 4,
                C.ServiceType.TENX_SC_16_PLEX_FLEX.id: 16,
            }.get(form.workflow.metadata["service_type_id"])
            for idx, row in df.iterrows():
                if pd.isna(barcode_id := row["barcode_id"]):
                    continue
                if not (parts := [b.strip() for b in str(barcode_id).split(";") if b.strip()]):
                    form.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue("'Barcode ID' is empty."))
                    continue
                barcodes = []
                for barcode in parts:
                    if (match := re.fullmatch(r"(?:BC)?0*(\d{1,3})", barcode.upper())) is None:
                        barcodes.append(barcode)
                    elif int(match.group(1)) == 0:
                        form.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"'{barcode}' is not a Flex probe barcode, expected e.g. 'BC001'."))
                    elif max_barcode is not None and int(match.group(1)) > max_barcode:
                        form.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"Barcode must be between BC001 and BC{max_barcode:03d} for this Flex kit."))
                    else:
                        barcodes.append(f"BC{int(match.group(1)):03d}")
                df.at[idx, "barcode_id"] = ";".join(barcodes)

            duplicated = df.duplicated(subset=["sample_pool", "barcode_id"] if "sample_pool" in df.columns else ["barcode_id"], keep=False) & pd.notna(df["barcode_id"])        
            for idx, _ in df.iterrows():
                if duplicated.at[idx]:
                    form.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("Duplicate 'Barcode ID' in the same 'Sample Pool' is not allowed."))
                    
            form.assert_valid()
            
            sample_pooling_table = form.workflow.tables["sample_pooling_table"]
        
            if form.flex_table is None:
                logger.error(f"{form.workflow.uuid}: Flex table is None.")
                raise Exception("Flex table is None.")
            
            flex_rows = sample_pooling_table["library_name"].isin(form.flex_libraries)
            barcodes = parsing.map_columns(sample_pooling_table, df, idx_columns=["sample_name", "sample_pool"], col="barcode_id")
            sample_pooling_table.loc[flex_rows, "mux_barcode"] = barcodes[flex_rows]
            # A CUSTOM service has no multiplexing type yet: Flex libraries with a probe barcode are probe-barcode
            # multiplexed, the ones without (only allowed for CUSTOM) are single-plex
            sample_pooling_table.loc[flex_rows & barcodes.notna(), "mux_type_id"] = C.MUXType.TENX_FLEX_PROBE.id

            library_table = form.workflow.tables["library_table"]
            abc_libraries = library_table.loc[library_table["library_type_id"] == C.LibraryType.TENX_SC_ABC_FLEX.id, "library_name"].values.tolist()
            sample_pooling_table.loc[sample_pooling_table["library_name"].isin(abc_libraries), "mux_barcode"] = sample_pooling_table.loc[sample_pooling_table["library_name"].isin(abc_libraries), "mux_barcode"].str.replace(r"(?<![^;])BC(?=\d{3}(?:;|$))", "AB", regex=True)
            form.workflow.tables["sample_pooling_table"] = sample_pooling_table

            # library_table from the previous step already has one library per pool and type; rebuilding
            # it here from the 'antibody_capture' flag dropped every other library type of a CUSTOM service
            return form.workflow.get_next_step(form).make_response()
        return route

