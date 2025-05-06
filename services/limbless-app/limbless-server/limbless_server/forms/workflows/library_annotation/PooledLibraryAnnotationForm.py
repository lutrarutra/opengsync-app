from typing import Optional

import pandas as pd

from flask import Response, url_for
from wtforms import SelectField

from limbless_db import models
from limbless_db.categories import LibraryType, GenomeRef, AssayType

from .... import logger, db
from ....tools import SpreadSheetColumn, tools
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .PoolMappingForm import PoolMappingForm


class PooledLibraryAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-pooled_library_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "pooled_library_annotation"

    assay_type = SelectField("Assay Type", choices=[(-1, "")] + AssayType.as_selectable(), coerce=int, default=None)

    columns = [
        SpreadSheetColumn("sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
        SpreadSheetColumn("library_type", "Library Type", "dropdown", 300, str, LibraryType.names()),
        SpreadSheetColumn("pool", "Pool", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
    ]

    def __init__(
        self, seq_request: models.SeqRequest, uuid: str,
        formdata: dict = {}, previous_form: Optional[MultiStepForm] = None
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=PooledLibraryAnnotationForm._workflow_name,
            step_name=PooledLibraryAnnotationForm._step_name, previous_form=previous_form,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=PooledLibraryAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, form_type='pooled', uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

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

        duplicate_sample_libraries = df.duplicated(subset=["sample_name", "library_type"])
        
        seq_request_samples = db.get_seq_request_samples_df(self.seq_request.id)

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(idx, "sample_name", "missing 'Sample Name'", "missing_value")

            if pd.isna(row["pool"]):
                self.spreadsheet.add_error(idx, "pool", "missing 'Pool'", "missing_value")

            if duplicate_sample_libraries.at[idx]:
                self.spreadsheet.add_error(idx, "sample_name", "Duplicate 'Sample Name' and 'Library Type'", "duplicate_value")

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                self.spreadsheet.add_error(idx, "library_type", f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request", "duplicate_value")

            if pd.isna(row["library_type"]):
                self.spreadsheet.add_error(idx, "library_type", "missing 'Library Type'", "missing_value")

            if pd.isna(row["genome"]):
                self.spreadsheet.add_error(idx, "genome", "missing 'Genome'", "missing_value")

        for sample_name, _df in df.groupby("sample_name"):
            if len(_df) > 1:
                if len(_df["genome"].unique()) > 1:
                    self.spreadsheet.add_general_error(f"Sample '{sample_name}' has multiple different genomes.")
        
        if len(self.spreadsheet._errors) > 0:
            return False
        
        df = self.__map_library_types(df)

        if assay_type != AssayType.CUSTOM:
            required_type_ids = [library_type.id for library_type in assay_type.library_types]
            optional_library_type_ids = [library_type.id for library_type in assay_type.optional_library_types]
            if assay_type.can_be_multiplexed:
                optional_library_type_ids.append(LibraryType.TENX_MULTIPLEXING_CAPTURE.id)

            for sample_name, _df in df.groupby("sample_name"):
                missing_library_type_mask = pd.Series(required_type_ids).isin(_df["library_type_id"])
                if not missing_library_type_mask.all():
                    missing_library_types = pd.Series(required_type_ids)[~missing_library_type_mask].apply(lambda x: LibraryType.get(x).name).to_list()
                    self.spreadsheet.add_general_error(f"Missing: {missing_library_types} library type(s) for sample '{sample_name}'")

                for idx, row in _df.iterrows():
                    library_type_id = row["library_type_id"]
                    if library_type_id not in required_type_ids and library_type_id not in optional_library_type_ids:
                        self.spreadsheet.add_error(
                            idx, "library_type",  # type: ignore
                            f"Library type '{LibraryType.get(library_type_id).name}' is not part of '{assay_type.name}' assay.",
                            "invalid_value"
                        )

        if len(self.spreadsheet._errors) > 0:
            return False
        
        df = self.__map_genome_ref(df)
        self.df = self.__map_existing_samples(df)
        return True
    
    def __map_library_types(self, df: pd.DataFrame) -> pd.DataFrame:
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        df["library_type_id"] = df["library_type"].map(library_type_map)
        df["library_name"] = df["sample_name"] + df["library_type_id"].apply(lambda x: f"_{LibraryType.get(x).identifier}")
        return df

    def __map_genome_ref(self, df: pd.DataFrame) -> pd.DataFrame:
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.display_name] = id
        
        df["genome_id"] = df["genome"].map(organism_map)
        return df

    def __map_existing_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        df["sample_id"] = None
        if self.metadata["project_id"] is None:
            return df
        if (project := db.get_project(self.metadata["project_id"])) is None:
            logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
            raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
        
        for sample in project.samples:
            df.loc[df["sample_name"] == sample.name, "sample_id"] = sample.id
        return df

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.metadata["assay_type_id"] = AssayType.get(self.assay_type.data).id

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
            "pool": []
        }

        pooling_table = {
            "sample_name": [],
            "library_name": [],
        }

        for (sample_name), _df in self.df.groupby("sample_name"):
            sample_table_data["sample_name"].append(sample_name)

            for _, row in _df.iterrows():
                genome = GenomeRef.get(int(row["genome_id"]))
                library_type = LibraryType.get(int(row["library_type_id"]))
                library_name = f"{sample_name}_{library_type.identifier}"

                library_table_data["library_name"].append(library_name)
                library_table_data["sample_name"].append(sample_name)
                library_table_data["genome"].append(genome.name)
                library_table_data["genome_id"].append(genome.id)
                library_table_data["library_type"].append(row["library_type"])
                library_table_data["library_type_id"].append(row["library_type_id"])
                library_table_data["pool"].append(row["pool"])

                pooling_table["sample_name"].append(sample_name)
                pooling_table["library_name"].append(library_name)

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None

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
        
        next_form = PoolMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()

        