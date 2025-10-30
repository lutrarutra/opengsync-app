import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import MUXType, AssayType, LibraryTypeEnum, LibraryType, SubmissionType

from .... import logger, db  # noqa
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm


class OCMAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-ocm_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "ocm_annotation"
    columns: list = [
        TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Pool Name", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=lambda x: str(x).strip().upper()),
    ]

    allowed_barcodes = [f"OB{i}" for i in range(1, 5)]

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return (current_step.metadata["submission_type_id"] == SubmissionType.POOLED_LIBRARIES.id) and (current_step.metadata["mux_type_id"] == MUXType.TENX_ON_CHIP.id)

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=OCMAnnotationForm._workflow_name, step_name=OCMAnnotationForm._step_name,
            uuid=uuid, formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.sample_pooling_table = self.tables["sample_pooling_table"]

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=OCMAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_ocm_reference', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True, df=self.sample_pooling_table
        )

    def fill_previous_form(self, previous_form: StepFile):
        df = previous_form.tables["sample_pooling_table"]
        df["barcode_id"] = df["mux_barcode"]
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        
        if df.empty:
            self.spreadsheet.add_general_error("Spreadsheet is empty..")
            return False

        def padded_barcode_id(s: str) -> str:
            number = ''.join(filter(str.isdigit, s))
            return f"OB{number}"
        
        df["barcode_id"] = df["barcode_id"].apply(lambda s: padded_barcode_id(s) if pd.notna(s) else None)
        duplicate_annotation = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)

        for i, (idx, row) in enumerate(df.iterrows()):
            if duplicate_annotation[i]:
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("Duplicate 'Barcode ID' in the same 'Sample Pool' is not allowed."))
                continue
            
            if row["barcode_id"] not in OCMAnnotationForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"Barcode ID must be one of {OCMAnnotationForm.allowed_barcodes}."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.sample_pooling_table["mux_barcode"] = utils.map_columns(self.sample_pooling_table, self.df, idx_columns=["sample_name", "sample_pool"], col="barcode_id")
        self.update_table("sample_pooling_table", self.sample_pooling_table, update_data=False)

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "library_type": [],
            "library_type_id": [],
        }

        assay_type_enum = AssayType.get(self.metadata["assay_type_id"])

        def add_library(sample_pool: str, library_type: LibraryTypeEnum):
            library_table_data["library_name"].append(f"{sample_pool}_{library_type.identifier}")
            library_table_data["sample_name"].append(sample_pool)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)

        for (sample_pool,), _ in self.sample_pooling_table.groupby(["sample_pool"], sort=False):
            for library_type in assay_type_enum.library_types:
                add_library(sample_pool, library_type)

            if self.metadata["antibody_capture"]:
                if assay_type_enum in [AssayType.TENX_SC_SINGLE_PLEX_FLEX, AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX]:
                    add_library(sample_pool, LibraryType.TENX_SC_ABC_FLEX)
                else:
                    add_library(sample_pool, LibraryType.TENX_ANTIBODY_CAPTURE)

            if self.metadata["vdj_b"]:
                add_library(sample_pool, LibraryType.TENX_VDJ_B)

            if self.metadata["vdj_t"]:
                add_library(sample_pool, LibraryType.TENX_VDJ_T)

            if self.metadata["vdj_t_gd"]:
                add_library(sample_pool, LibraryType.TENX_VDJ_T_GD)

            if self.metadata["crispr_screening"]:
                add_library(sample_pool, LibraryType.TENX_CRISPR_SCREENING)

        self.update_data()

        if self.metadata["submission_type_id"] == SubmissionType.POOLED_LIBRARIES.id:
            next_form = PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)

        return next_form.make_response()