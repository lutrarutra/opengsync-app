from typing import Optional

import pandas as pd

from flask import Response

from limbless_db import models
from limbless_db.categories import LibraryType, GenomeRef

from .... import logger, db
from ....tools import SpreadSheetColumn, tools
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from ...SpreadsheetInput import SpreadsheetInput
from .CMOReferenceInputForm import CMOReferenceInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .GenomeRefMappingForm import GenomeRefMappingForm
from .FRPAnnotationForm import FRPAnnotationForm
from .LibraryMappingForm import LibraryMappingForm
from .SampleAnnotationForm import SampleAnnotationForm
from .FeatureReferenceInputForm import FeatureReferenceInputForm


class LibraryAnnotationForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-2.raw.html"

    columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
        "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
        "seq_depth": SpreadSheetColumn("D", "seq_depth", "Sequencing Depth", "numeric", 150, float, clean_up_fnc=lambda x: tools.parse_float(x)),
    }

    def __init__(
        self, seq_request: models.SeqRequest,
        formdata: dict = {}, uuid: Optional[str] = None
    ):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = formdata.get("file_uuid")
        TableDataForm.__init__(self, uuid=uuid, dirname="library_annotation")
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=LibraryAnnotationForm.columns, csrf_token=csrf_token,
            post_url="", formdata=formdata, allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        duplicate_sample_libraries = df.duplicated(subset=["sample_name", "library_type"])
        
        seq_request_samples = db.get_seq_request_samples_df(self.seq_request.id)

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(i + 1, "sample_name", "missing 'Sample Name'", "missing_value")
                continue

            if duplicate_sample_libraries.at[idx]:
                self.spreadsheet.add_error(i + 1, "sample_name", "Duplicate 'Sample Name' and 'Library Type'", "duplicate_value")

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                self.spreadsheet.add_error(i + 1, "library_type", f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request", "duplicate_value")

            if pd.isna(row["library_type"]):
                self.spreadsheet.add_error(i + 1, "library_type", "missing 'Library Type'", "missing_value")

            if pd.isna(row["genome"]):
                self.spreadsheet.add_error(i + 1, "genome", "missing 'Genome'", "missing_value")

            if pd.notna(row["seq_depth"]):
                try:
                    if isinstance(row["seq_depth"], str):
                        row["seq_depth"] = row["seq_depth"].strip().replace(" ", "")

                    row["seq_depth"] = float(row["seq_depth"])
                except ValueError:
                    self.spreadsheet.add_error(i + 1, "seq_depth", "invalid 'Sequencing Depth'", "invalid_value")

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def __map_library_types(self):
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        self.df["library_type_id"] = self.df["library_type"].map(library_type_map)
        self.df["library_name"] = self.df["sample_name"] + self.df["library_type_id"].apply(lambda x: f"_{LibraryType.get(x).identifier}")

    def __map_genome_ref(self):
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.display_name] = id
        
        self.df["genome_id"] = self.df["genome"].map(organism_map)

    def __map_existing_samples(self):
        self.df["sample_id"] = None
        if self.metadata["project_id"] is None:
            return
        if (project := db.get_project(self.metadata["project_id"])) is None:
            logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
            raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
        
        for sample in project.samples:
            self.df.loc[self.df["sample_name"] == sample.name, "sample_id"] = sample.id

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.__map_library_types()
        self.__map_genome_ref()
        self.__map_existing_samples()
        
        self.add_table("library_table", self.df)
        self.update_data()

        if self.df["genome_id"].isna().any():
            organism_mapping_form = GenomeRefMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            organism_mapping_form.prepare()
            return organism_mapping_form.make_response()
        
        if self.df["library_type_id"].isna().any():
            library_mapping_form = LibraryMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            library_mapping_form.prepare()
            return library_mapping_form.make_response()
        
        if self.df["library_type_id"].isin([
            LibraryType.TENX_MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response()
        
        if (self.df["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if (self.df["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id).any():
            feature_reference_input_form = FeatureReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return feature_reference_input_form.make_response()
        
        if LibraryType.TENX_SC_GEX_FLEX.id in self.df["library_type_id"].values:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()
    
        sample_annotation_form = SampleAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()

        