from typing import Optional

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import AssayType, GenomeRef, LibraryType, LibraryTypeEnum, GenomeRefEnum

from .... import logger, db
from ....tools import SpreadSheetColumn
from ...MultiStepForm import MultiStepForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from ...SpreadsheetInput import SpreadsheetInput


class DefineMultiplexedSamplesForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-define_mux_samples.html"
    _workflow_name = "library_annotation"
    _step_name = "define_mux_samples"

    columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 300, str),
        "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 300, str, GenomeRef.names()),
        "pool": SpreadSheetColumn("C", "pool", "Pool", "text", 300, str),
    }

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=DefineMultiplexedSamplesForm._workflow_name,
            step_name=DefineMultiplexedSamplesForm._step_name, previous_form=previous_form,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=DefineMultiplexedSamplesForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, uuid=self.uuid, form_type="tech-multiplexed"),
            formdata=formdata, allow_new_rows=True
        )

        self.assay_type = AssayType.get(int(self.metadata["assay_type_id"]))
        self.antibody_multiplexing = self.metadata["antibody_multiplexing"]
        self.nuclei_isolation = self.metadata["nuclei_isolation"]
        self.antibody_capture = self.metadata["antibody_capture"]
        self.vdj_b = self.metadata["vdj_b"]
        self.vdj_t = self.metadata["vdj_t"]
        self.vdj_t_gd = self.metadata["vdj_t_gd"]
        self.crispr_screening = self.metadata["crispr_screening"]

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        sample_name_counts = df["sample_name"].value_counts()
        seq_request_samples = db.get_seq_request_samples_df(self.seq_request.id)

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
        if self.antibody_multiplexing:
            selected_library_types.append(LibraryType.TENX_MULTIPLEXING_CAPTURE.abbreviation)

        if df["pool"].isna().all():
            for i, (idx, row) in enumerate(df.iterrows()):
                if self.assay_type == AssayType.TENX_SC_4_PLEX_FLEX:
                    df.at[idx, "pool"] = f"flex_pool_{i // 4 + 1}"
                elif self.assay_type == AssayType.TENX_SC_16_PLEX_FLEX:
                    df.at[idx, "pool"] = f"flex_pool_{i // 16 + 1}"
                else:
                    df.at[idx, "pool"] = f"hto_pool_{i + 1}"

        for i, (_, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(i + 1, "sample_name", "missing 'Sample Name'", "missing_value")
            elif sample_name_counts[row["sample_name"]] > 1:
                self.spreadsheet.add_error(i + 1, "sample_name", "duplicate 'Sample Name'", "duplicate_value")

            duplicate_library = (seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.abbreviation).isin(selected_library_types))
            if (duplicate_library).any():
                library_type = seq_request_samples.loc[duplicate_library, "library_type"].iloc[0]  # type: ignore
                self.spreadsheet.add_error(i + 1, "sample_name", f"You already have '{library_type.abbreviation}'-library from sample {row['sample_name']} in the request", "duplicate_value")

            if pd.isna(row["genome"]):
                self.spreadsheet.add_error(i + 1, "genome", "missing 'Genome'", "missing_value")

            if not df["pool"].isna().all():
                if pd.isna(row["pool"]):
                    self.spreadsheet.add_error(i + 1, "pool", "missing 'Pool'", "missing_value")

            if pd.notna(row["pool"]) and len(str(row["pool"])) < 4:
                self.spreadsheet.add_error(i + 1, "pool", "Pool must be at least 4 characters long", "invalid_value")

            if len(df[df["pool"] == row["pool"]]["genome"].unique()) > 1:
                self.spreadsheet.add_error(i + 1, "pool", "All samples in a pool must have the same genome", "invalid_input")
                self.spreadsheet.add_error(i + 1, "genome", "All samples in a pool must have the same genome", "invalid_input")
        
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

        pooling_table = {
            "sample_name": [],
            "library_name": [],
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

            if self.antibody_multiplexing:
                add_library(sample_pool, LibraryType.TENX_MULTIPLEXING_CAPTURE, genome)

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
                    pooling_table["sample_name"].append(sample_name)
                    pooling_table["library_name"].append(f"{sample_pool}_{library_type.identifier}")
                if self.antibody_multiplexing:
                    pooling_table["sample_name"].append(sample_name)
                    pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_MULTIPLEXING_CAPTURE.identifier}")
                if self.antibody_capture:
                    pooling_table["sample_name"].append(sample_name)
                    if self.assay_type in [AssayType.TENX_SC_SINGLE_PLEX_FLEX, AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX]:
                        pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_SC_ABC_FLEX.identifier}")
                    else:
                        pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_ANTIBODY_CAPTURE.identifier}")
                if self.vdj_b:
                    pooling_table["sample_name"].append(sample_name)
                    pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_VDJ_B.identifier}")
                if self.vdj_t:
                    pooling_table["sample_name"].append(sample_name)
                    pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_VDJ_T.identifier}")
                if self.vdj_t_gd:
                    pooling_table["sample_name"].append(sample_name)
                    pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_VDJ_T_GD.identifier}")
                if self.crispr_screening:
                    pooling_table["sample_name"].append(sample_name)
                    pooling_table["library_name"].append(f"{sample_pool}_{LibraryType.TENX_CRISPR_SCREENING.identifier}")

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None
        library_table = library_table.reset_index(drop=True)

        sample_table = pd.DataFrame(sample_table_data)
        sample_table["sample_id"] = None
        sample_table["cmo_sequence"] = None
        sample_table["cmo_pattern"] = None
        sample_table["cmo_read"] = None
        sample_table["flex_barcode"] = None
        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.get_project(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        pooling_table = pd.DataFrame(pooling_table)

        self.add_table("library_table", library_table)
        self.add_table("sample_table", sample_table)
        self.add_table("pooling_table", pooling_table)
        self.update_data()
        
        if ((library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id) | (library_table["library_type_id"] == LibraryType.TENX_SC_ABC_FLEX.id)).any():
            feature_reference_input_form = FeatureAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return feature_reference_input_form.make_response()
        
        if (library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        sample_annotation_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()