import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import AssayType, GenomeRef, LibraryType, LibraryTypeEnum, GenomeRefEnum, MUXType

from .... import logger, db
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, DropdownColumn, InvalidCellValue, MissingCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class DefineMultiplexedSamplesForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-define_mux_samples.html"
    _workflow_name = "library_annotation"
    _step_name = "define_mux_samples"

    columns = [
        TextColumn("sample_name", "Sample Name", 300, required=True, max_length=models.Sample.name.type.length, min_length=4, validation_fnc=utils.check_string),
        DropdownColumn("genome", "Genome", 300, choices=GenomeRef.names(), required=True),
        TextColumn("pool", "Pool", 300, max_length=models.Library.name.type.length, min_length=4, validation_fnc=utils.check_string),
    ]

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
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=DefineMultiplexedSamplesForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, uuid=self.uuid, form_type="tech-multiplexed"),
            formdata=formdata, allow_new_rows=True
        )

        self.assay_type = AssayType.get(int(self.metadata["assay_type_id"]))
        self.mux_type = MUXType.get(self.metadata["mux_type_id"])
        self.antibody_capture = self.metadata["antibody_capture"]
        self.vdj_b = self.metadata["vdj_b"]
        self.vdj_t = self.metadata["vdj_t"]
        self.vdj_t_gd = self.metadata["vdj_t_gd"]
        self.crispr_screening = self.metadata["crispr_screening"]

    def fill_previous_form(self, previous_form: StepFile):
        sample_pooling_table = previous_form.tables["sample_pooling_table"].rename(
            columns={"sample_pool": "pool"}
        )
        sample_pooling_table = sample_pooling_table.drop_duplicates(subset=["sample_name", "pool"])
        genome_mapping = {}
        for _, row in previous_form.tables["library_table"].iterrows():
            genome_mapping[row["library_name"]] = GenomeRef.get(row["genome_id"]).display_name

        sample_pooling_table["genome"] = sample_pooling_table["library_name"].map(genome_mapping)
        logger.debug(sample_pooling_table)
        self.spreadsheet.set_data(sample_pooling_table)

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        sample_name_counts = df["sample_name"].value_counts()
        seq_request_samples = db.pd.get_seq_request_samples(self.seq_request.id)

        selected_library_types = [t.abbreviation for t in self.assay_type.library_types]
        if self.antibody_capture:
            if self.assay_type in [AssayType.TENX_SC_SINGLE_PLEX_FLEX, AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX]:
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
                if self.assay_type == AssayType.TENX_SC_4_PLEX_FLEX:
                    df.at[idx, "pool"] = f"flex_pool_{i // 4 + 1}"
                elif self.assay_type == AssayType.TENX_SC_16_PLEX_FLEX:
                    df.at[idx, "pool"] = f"flex_pool_{i // 16 + 1}"
                else:
                    df.at[idx, "pool"] = f"hto_pool_{i + 1}"

        for idx, row in df.iterrows():
            if sample_name_counts[row["sample_name"]] > 1:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("duplicate 'Sample Name'"))

            duplicate_library = (seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.abbreviation).isin(selected_library_types))
            if (duplicate_library).any():
                library_type = seq_request_samples.loc[duplicate_library, "library_type"].iloc[0]  # type: ignore
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue(f"You already have '{library_type.abbreviation}'-library from sample {row['sample_name']} in the request"))

            if not df["pool"].isna().all():
                if pd.isna(row["pool"]):
                    self.spreadsheet.add_error(idx, "pool", MissingCellValue("missing 'Pool'"))

            if pd.notna(row["pool"]) and len(str(row["pool"])) < 4:
                self.spreadsheet.add_error(idx, "pool", InvalidCellValue("Pool must be at least 4 characters long"))

            if len(df[df["pool"] == row["pool"]]["genome"].unique()) > 1:
                self.spreadsheet.add_error(idx, "pool", InvalidCellValue("All samples in a pool must have the same genome"))
                self.spreadsheet.add_error(idx, "genome", InvalidCellValue("All samples in a pool must have the same genome"))
        
        genome_map = {}
        for id, e in GenomeRef.as_tuples():
            genome_map[e.display_name] = id
        
        df["genome_id"] = df["genome"].map(genome_map)

        if self.spreadsheet._errors:
            return False
        
        self.df = df

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_table_data = {
            "sample_name": [],
        }

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "genome": [],
            "genome_id": [],
            "library_type": [],
            "library_type_id": [],
        }

        sample_pooling_table = {
            "sample_name": [],
            "library_name": [],
            "sample_pool": [],
        }

        def add_library(sample_pool: str, library_type: LibraryTypeEnum, genome: GenomeRefEnum):
            library_name = f"{sample_pool}_{library_type.identifier}"
            
            library_table_data["library_name"].append(library_name)
            library_table_data["sample_name"].append(sample_pool)
            library_table_data["genome"].append(genome.name)
            library_table_data["genome_id"].append(genome.id)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)

        for (sample_pool, genome_id), _df in self.df.groupby(["pool", "genome_id"]):
            genome = GenomeRef.get(int(genome_id))
            
            for library_type in self.assay_type.library_types:
                add_library(sample_pool, library_type, genome)
            
            if self.antibody_capture:
                if self.assay_type in [AssayType.TENX_SC_SINGLE_PLEX_FLEX, AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX]:
                    add_library(sample_pool, LibraryType.TENX_SC_ABC_FLEX, genome)
                else:
                    add_library(sample_pool, LibraryType.TENX_ANTIBODY_CAPTURE, genome)

            if self.mux_type == MUXType.TENX_OLIGO:
                add_library(sample_pool, LibraryType.TENX_MUX_OLIGO, genome)

            if self.vdj_b:
                add_library(sample_pool, LibraryType.TENX_VDJ_B, genome)

            if self.vdj_t:
                add_library(sample_pool, LibraryType.TENX_VDJ_T, genome)

            if self.vdj_t_gd:
                add_library(sample_pool, LibraryType.TENX_VDJ_T_GD, genome)

            if self.crispr_screening:
                add_library(sample_pool, LibraryType.TENX_CRISPR_SCREENING, genome)

            for _, row in _df.iterrows():
                sample_name = row["sample_name"]
                sample_table_data["sample_name"].append(sample_name)
                for library_type in self.assay_type.library_types:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    sample_pooling_table["library_name"].append(f"{sample_pool}_{library_type.identifier}")
                if self.mux_type == MUXType.TENX_OLIGO:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_MUX_OLIGO.identifier}")
                if self.antibody_capture:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    if self.assay_type in [AssayType.TENX_SC_SINGLE_PLEX_FLEX, AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX]:
                        sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_SC_ABC_FLEX.identifier}")
                    else:
                        sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_ANTIBODY_CAPTURE.identifier}")
                if self.vdj_b:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_VDJ_B.identifier}")
                if self.vdj_t:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_VDJ_T.identifier}")
                if self.vdj_t_gd:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_VDJ_T_GD.identifier}")
                if self.crispr_screening:
                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)
                    sample_pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_CRISPR_SCREENING.identifier}")

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None
        library_table = library_table.reset_index(drop=True)

        sample_table = pd.DataFrame(sample_table_data)
        sample_table["sample_id"] = None
        
        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.projects.get(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        sample_pooling_table = pd.DataFrame(sample_pooling_table)
        sample_pooling_table["mux_type_id"] = self.mux_type.id
        sample_pooling_table["mux_barcode"] = None

        self.add_table("library_table", library_table)
        self.add_table("sample_table", sample_table)
        self.add_table("sample_pooling_table", sample_pooling_table)
        self.update_data()

        if FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()