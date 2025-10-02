import pandas as pd

from flask import Response, url_for
from wtforms import SelectField, BooleanField

from opengsync_db import models
from opengsync_db.categories import LibraryType, GenomeRef, AssayType, MUXType

from .... import logger, db
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, CategoricalDropDown, InvalidCellValue, MissingCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .PoolMappingForm import PoolMappingForm


class PooledLibraryAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-pooled_library_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "pooled_library_annotation"

    assay_type = SelectField("Assay Type", choices=[(-1, "")] + AssayType.as_selectable(), coerce=int, default=None)
    ocm_multiplexing = BooleanField("On-Chip Multiplexing for 10X GEM-X Libraries", description="Multiple samples per library using 10X On-Chip Multiplexing", default=False)
    antibody_multiplexing = BooleanField("10X Cell Surface Protein Capture & Antibody Multiplexing in the same library.", description="Multiple samples per library with antibody-based cell tagging. Only available with cell surface protein capture.", default=False)
    nuclei_isolation = BooleanField("Nuclei Isolation", default=False, description="I have isolated nuclei from my samples.")

    columns = [
        TextColumn("sample_name", "Sample Name", 200, required=True, max_length=models.Library.sample_name.type.length, min_length=4, validation_fnc=utils.check_string),
        CategoricalDropDown("genome_id", "Genome", 200, categories=dict(GenomeRef.as_selectable()), required=True),
        CategoricalDropDown("library_type_id", "Library Type", 300, categories=dict(LibraryType.as_selectable()), required=True),
        TextColumn("pool", "Pool", 200, required=True, max_length=models.Pool.name.type.length, min_length=4),
    ]

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.metadata["workflow_type"] == "pooled"

    def __init__(
        self, seq_request: models.SeqRequest, uuid: str,
        formdata: dict | None = None
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=PooledLibraryAnnotationForm._workflow_name,
            step_name=PooledLibraryAnnotationForm._step_name,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=PooledLibraryAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, form_type='pooled', uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def fill_previous_form(self, previous_form: StepFile):
        df = previous_form.tables["library_table"]
        self.spreadsheet.set_data(df)
        assay_type_id = previous_form.metadata.get("assay_type_id")
        self.antibody_multiplexing.data = previous_form.metadata.get("antibody_multiplexing", False)
        self.nuclei_isolation.data = previous_form.metadata.get("nuclei_isolation", False)
        self.assay_type.data = assay_type_id

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
        
        if self.assay_type.data is None or self.assay_type.data == -1:
            self.assay_type.errors = ("Assay Type is required.",)
            return False
        try:
            assay_type = AssayType.get(self.assay_type.data)
        except ValueError:
            self.assay_type.errors = ("Invalid Assay Type.",)
            return False
    
        df = self.spreadsheet.df
        df["library_type"] = df["library_type_id"].apply(lambda x: LibraryType.get(int(x)).display_name if pd.notna(x) else None)
        df["genome"] = df["genome_id"].apply(lambda x: GenomeRef.get(int(x)).display_name if pd.notna(x) else None)

        duplicate_sample_libraries = df.duplicated(subset=["sample_name", "library_type"])
        seq_request_samples = db.pd.get_seq_request_samples(self.seq_request.id)

        for idx, row in df.iterrows():
            if duplicate_sample_libraries.at[idx]:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("Duplicate 'Sample Name' and 'Library Type'"))

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                self.spreadsheet.add_error(idx, "library_type_id", DuplicateCellValue(f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request"))

        for sample_name, _df in df.groupby("sample_name"):
            if len(_df) > 1:
                if len(_df["genome_id"].unique()) > 1:
                    self.spreadsheet.add_general_error(f"Sample '{sample_name}' has multiple different genomes.")
        
        if len(self.spreadsheet._errors) > 0:
            return False

        if self.ocm_multiplexing.data and LibraryType.TENX_MUX_OLIGO.id in df["library_type_id"].values:
            self.spreadsheet.add_general_error("It is not possible to use '10X On-Chip Multiplexing' with '10X Multiplexing Oligo' library type.")

        if assay_type != AssayType.CUSTOM:
            required_type_ids = [library_type.id for library_type in assay_type.library_types]
            optional_library_type_ids = [library_type.id for library_type in assay_type.optional_library_types]
            if assay_type.oligo_multiplexing:
                optional_library_type_ids.append(LibraryType.TENX_MUX_OLIGO.id)

            for sample_name, _df in df.groupby("sample_name"):
                missing_library_type_mask = pd.Series(required_type_ids).isin(_df["library_type_id"])
                if not missing_library_type_mask.all():
                    missing_library_types = pd.Series(required_type_ids)[~missing_library_type_mask].apply(lambda x: LibraryType.get(x).name).to_list()
                    self.spreadsheet.add_general_error(f"Missing: {missing_library_types} library type(s) for sample '{sample_name}'")

                if self.antibody_multiplexing.data:
                    if LibraryType.TENX_ANTIBODY_CAPTURE.id not in _df["library_type_id"].values:
                        self.spreadsheet.add_general_error(f"Antibody-based cell hashing multiplexing requires '10X Antibody Capture' library type for sample '{sample_name}'")

                for idx, row in _df.iterrows():
                    library_type_id = row["library_type_id"]
                    if library_type_id not in required_type_ids and library_type_id not in optional_library_type_ids:
                        self.spreadsheet.add_error(
                            idx, "library_type_id",  # type: ignore
                            InvalidCellValue(f"Library type '{LibraryType.get(library_type_id).name}' is not part of '{assay_type.name}' assay."),
                        )
                    elif library_type_id == LibraryType.TENX_MUX_OLIGO.id and self.antibody_multiplexing.data:
                        self.spreadsheet.add_error(
                            idx, "library_type_id",  # type: ignore
                            InvalidCellValue("Antibody-based cell hashing multiplexing cannot be combined with 10X Multiplexing Oligo."),
                        )


        if len(self.spreadsheet._errors) > 0:
            return False
        
        df["library_name"] = df["sample_name"] + df["library_type_id"].apply(lambda x: f"_{LibraryType.get(x).identifier}")
        self.df = self.__map_existing_samples(df)

        return True

    def __map_existing_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        df["sample_id"] = None
        if self.metadata["project_id"] is None:
            return df
        
        if (project := db.projects.get(self.metadata["project_id"])) is None:
            logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
            raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
        
        for sample in project.samples:
            df.loc[df["sample_name"] == sample.name, "sample_id"] = sample.id
        return df

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.metadata["assay_type_id"] = AssayType.get(self.assay_type.data).id
        self.metadata["antibody_multiplexing"] = self.antibody_multiplexing.data
        
        self.metadata["mux_type_id"] = None
        if self.ocm_multiplexing.data:
            self.metadata["mux_type_id"] = MUXType.TENX_ON_CHIP.id
        elif LibraryType.TENX_MUX_OLIGO.id in self.df["library_type_id"].values:
            self.metadata["mux_type_id"] = MUXType.TENX_OLIGO.id
        elif self.antibody_multiplexing.data:
            self.metadata["mux_type_id"] = MUXType.TENX_ABC_HASH.id
        elif self.assay_type.data in {AssayType.TENX_SC_16_PLEX_FLEX, AssayType.TENX_SC_4_PLEX_FLEX}:
            self.metadata["mux_type_id"] = MUXType.TENX_FLEX_PROBE.id

        self.metadata["nuclei_isolation"] = self.nuclei_isolation.data

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "genome": [],
            "genome_id": [],
            "library_type": [],
            "library_type_id": [],
            "pool": []
        }

        sample_pooling_table = {
            "sample_name": [],
            "sample_pool": [],
            "library_name": [],
        }

        for (library_type_id,), _df in self.df.groupby(["library_type_id"], sort=False):
            library_type = LibraryType.get(int(library_type_id))  # type: ignore
            for _, row in _df.iterrows():
                genome = GenomeRef.get(int(row["genome_id"]))
                library_name = f"{row['sample_name']}_{library_type.identifier}"
                library_table_data["library_name"].append(library_name)
                library_table_data["sample_name"].append(row["sample_name"])
                library_table_data["genome"].append(genome.display_name)
                library_table_data["genome_id"].append(genome.id)
                library_table_data["library_type"].append(library_type.display_name)
                library_table_data["library_type_id"].append(library_type.id)
                library_table_data["pool"].append(row["pool"])

                sample_pooling_table["sample_name"].append(row["sample_name"])
                sample_pooling_table["sample_pool"].append(row["sample_name"])
                sample_pooling_table["library_name"].append(library_name)

        sample_pooling_table = pd.DataFrame(sample_pooling_table)
        sample_pooling_table["mux_type_id"] = self.metadata["mux_type_id"]
        self.add_table("sample_pooling_table", sample_pooling_table)
        
        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None
        self.add_table("library_table", library_table)

        sample_table = self.df[["sample_name"]].drop_duplicates(keep="first").reset_index(drop=True)
        sample_table["sample_id"] = None

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.projects.get(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        self.add_table("sample_table", sample_table)
        self.update_data()
        
        next_form = PoolMappingForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()

        