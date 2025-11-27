import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import ServiceType, LibraryType, LibraryTypeEnum, MUXType

from .... import logger, db  # noqa F401
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, MissingCellValue, DuplicateCellValue, DropdownColumn
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm
from .CustomAssayAnnotationForm import CustomAssayAnnotationFrom
from .ParseMuxAnnotationForm import ParseMuxAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm
from .CompleteSASForm import CompleteSASForm


class DefineMultiplexedSamplesForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-define_mux_samples.html"
    _workflow_name = "library_annotation"
    _step_name = "define_mux_samples"

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.metadata["mux_type_id"] is not None

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=DefineMultiplexedSamplesForm._workflow_name,
            step_name=DefineMultiplexedSamplesForm._step_name,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.sample_table = self.tables["sample_table"]
        self.columns: list = [
            DropdownColumn("sample_name", "Sample Name", 300, required=True, choices=self.sample_table["sample_name"].tolist(), read_only=False),
            TextColumn("pool", "Sample Pool", 300, max_length=models.Library.name.type.length, min_length=4, validation_fnc=utils.check_string),
        ]
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_mux_definition_form', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True, df=self.sample_table
        )

        self.service_type = ServiceType.get(int(self.metadata["service_type_id"]))
        self.mux_type = MUXType.get(self.metadata["mux_type_id"])
        self.antibody_capture = self.metadata["antibody_capture"]
        self.vdj_b = self.metadata["vdj_b"]
        self.vdj_t = self.metadata["vdj_t"]
        self.vdj_t_gd = self.metadata["vdj_t_gd"]
        self.crispr_screening = self.metadata["crispr_screening"]
        self.parse_tcr = self.metadata.get("parse_tcr", False)
        self.parse_bcr = self.metadata.get("parse_bcr", False)
        self.parse_crispr = self.metadata.get("parse_crispr", False)

    def fill_previous_form(self, previous_form: StepFile):
        sample_pooling_table = previous_form.tables["sample_pooling_table"].rename(
            columns={"sample_pool": "pool"}
        )
        sample_pooling_table = sample_pooling_table.drop_duplicates(subset=["sample_name", "pool"])
        self.spreadsheet.set_data(sample_pooling_table)

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        seq_request_samples = db.pd.get_seq_request_samples(self.seq_request.id)

        selected_library_types = [t.abbreviation for t in self.service_type.library_types]
        if self.antibody_capture:
            if self.service_type in [ServiceType.TENX_SC_SINGLE_PLEX_FLEX, ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]:
                selected_library_types.append(LibraryType.TENX_SC_ABC_FLEX.abbreviation)
            else:
                selected_library_types.append(LibraryType.TENX_ANTIBODY_CAPTURE.abbreviation)
        if self.vdj_b:
            selected_library_types.append(LibraryType.TENX_VDJ_B.abbreviation)
        if self.vdj_t:
            selected_library_types.append(LibraryType.TENX_VDJ_T.abbreviation)
        if self.vdj_t_gd:
            selected_library_types.append(LibraryType.TENX_VDJ_T_GD.abbreviation)
        if self.crispr_screening:
            selected_library_types.append(LibraryType.TENX_CRISPR_SCREENING.abbreviation)
        if self.mux_type == MUXType.TENX_OLIGO:
            selected_library_types.append(LibraryType.TENX_MUX_OLIGO.abbreviation)
        
        if df["pool"].isna().all():
            for i, (idx, row) in enumerate(df.iterrows()):
                if self.service_type == ServiceType.TENX_SC_4_PLEX_FLEX:
                    df.at[idx, "pool"] = f"flex_pool_{i // 4 + 1}"  # type: ignore
                elif self.service_type == ServiceType.TENX_SC_16_PLEX_FLEX:
                    df.at[idx, "pool"] = f"flex_pool_{i // 16 + 1}"  # type: ignore
                else:
                    df.at[idx, "pool"] = f"hto_pool_{i + 1}"  # type: ignore

        duplicate_definition = df.duplicated(subset=["sample_name", "pool"], keep=False)

        for idx, row in df.iterrows():
            if duplicate_definition.at[idx]:
                self.spreadsheet.add_error(idx, "pool", DuplicateCellValue(f"Sample '{row['sample_name']}' is assigned to pool '{row['pool']}' multiple times."))

            duplicate_library = (seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.abbreviation).isin(selected_library_types))
            if (duplicate_library).any():
                library_type = seq_request_samples.loc[duplicate_library, "library_type"].iloc[0]  # type: ignore
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue(f"You already have '{library_type.abbreviation}'-library from sample {row['sample_name']} in the request"))

            if not df["pool"].isna().all():
                if pd.isna(row["pool"]):
                    self.spreadsheet.add_error(idx, "pool", MissingCellValue("missing 'Pool'"))

            if pd.notna(row["pool"]) and len(str(row["pool"])) < 4:
                self.spreadsheet.add_error(idx, "pool", InvalidCellValue("Pool must be at least 4 characters long"))

        if self.spreadsheet._errors:
            return False
        
        self.df = df

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.service_type == ServiceType.CUSTOM:
            sample_pooling_table = {
                "sample_pool": [],
                "sample_name": [],
            }
            for (sample_name, sample_pool), _ in self.df.groupby(["sample_name", "pool"], sort=False):
                sample_pooling_table["sample_pool"].append(sample_pool)
                sample_pooling_table["sample_name"].append(sample_name)
                
            sample_pooling_table = pd.DataFrame(sample_pooling_table)
            self.add_table("sample_pooling_table", sample_pooling_table)
            self.update_data()
            next_form = CustomAssayAnnotationFrom(seq_request=self.seq_request, uuid=self.uuid)
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

        def add_library(sample_pool: str, library_type: LibraryTypeEnum):
            library_name = f"{sample_pool}_{library_type.identifier}"
            
            library_table_data["library_name"].append(library_name)
            library_table_data["sample_name"].append(sample_pool)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)

        def link_sample(sample_name: str, sample_pool: str, library_type: LibraryTypeEnum):
            sample_pooling_table["sample_name"].append(sample_name)
            sample_pooling_table["sample_pool"].append(sample_pool)
            sample_pooling_table["library_name"].append(f"{sample_pool}_{library_type.identifier}")

        for (sample_pool,), _df in self.df.groupby(["pool"], sort=False):
            for library_type in self.service_type.library_types:
                add_library(sample_pool, library_type)
            
            if self.antibody_capture:
                if self.service_type in [ServiceType.TENX_SC_SINGLE_PLEX_FLEX, ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]:
                    add_library(sample_pool, LibraryType.TENX_SC_ABC_FLEX)
                else:
                    add_library(sample_pool, LibraryType.TENX_ANTIBODY_CAPTURE)

            if self.mux_type == MUXType.TENX_OLIGO:
                add_library(sample_pool, LibraryType.TENX_MUX_OLIGO)
            if self.vdj_b:
                add_library(sample_pool, LibraryType.TENX_VDJ_B)
            if self.vdj_t:
                add_library(sample_pool, LibraryType.TENX_VDJ_T)
            if self.vdj_t_gd:
                add_library(sample_pool, LibraryType.TENX_VDJ_T_GD)
            if self.crispr_screening:
                add_library(sample_pool, LibraryType.TENX_CRISPR_SCREENING)
            if self.parse_crispr:
                add_library(sample_pool, LibraryType.PARSE_SC_CRISPR)
            if self.parse_tcr:
                add_library(sample_pool, LibraryType.PARSE_EVERCODE_TCR)
            if self.parse_bcr:
                add_library(sample_pool, LibraryType.PARSE_EVERCODE_BCR)

            for _, row in _df.iterrows():
                sample_name = row["sample_name"]

                for library_type in self.service_type.library_types:
                    link_sample(sample_name, sample_pool, library_type)
                if self.mux_type == MUXType.TENX_OLIGO:
                    link_sample(sample_name, sample_pool, LibraryType.TENX_MUX_OLIGO)
                if self.antibody_capture:
                    if self.service_type in [ServiceType.TENX_SC_SINGLE_PLEX_FLEX, ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]:
                        link_sample(sample_name, sample_pool, LibraryType.TENX_SC_ABC_FLEX)
                    else:
                        link_sample(sample_name, sample_pool, LibraryType.TENX_ANTIBODY_CAPTURE)
                if self.vdj_b:
                    link_sample(sample_name, sample_pool, LibraryType.TENX_VDJ_B)
                if self.vdj_t:
                    link_sample(sample_name, sample_pool, LibraryType.TENX_VDJ_T)
                if self.vdj_t_gd:
                    link_sample(sample_name, sample_pool, LibraryType.TENX_VDJ_T_GD)
                if self.crispr_screening:
                    link_sample(sample_name, sample_pool, LibraryType.TENX_CRISPR_SCREENING)
                if self.parse_crispr:
                    link_sample(sample_name, sample_pool, LibraryType.PARSE_SC_CRISPR)
                if self.parse_tcr:
                    link_sample(sample_name, sample_pool, LibraryType.PARSE_EVERCODE_TCR)
                if self.parse_bcr:
                    link_sample(sample_name, sample_pool, LibraryType.PARSE_EVERCODE_BCR)

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None
        library_table = library_table.reset_index(drop=True)

        sample_pooling_table = pd.DataFrame(sample_pooling_table)
        sample_pooling_table["mux_type_id"] = self.mux_type.id
        sample_pooling_table["mux_barcode"] = None

        self.add_table("library_table", library_table)
        self.add_table("sample_pooling_table", sample_pooling_table)
        self.update_data()

        if OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseMuxAnnotationForm.is_applicable(self):
            next_form = ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseCRISPRGuideAnnotationForm.is_applicable(self):
            next_form = ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()