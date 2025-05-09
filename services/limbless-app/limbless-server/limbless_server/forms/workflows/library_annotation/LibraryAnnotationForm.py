from typing import Optional

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType, GenomeRef

from .... import logger, db
from ....tools import tools
from ....tools.spread_sheet_components import InvalidCellValue, MissingCellValue, DuplicateCellValue, TextColumn, DropdownColumn, FloatColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .CMOAnnotationForm import CMOAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm


class LibraryAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-library_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "library_annotation"

    columns = [
        TextColumn("sample_name", "Sample Name", 200, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        DropdownColumn("genome", "Genome", 200, choices=GenomeRef.names(), required=True),
        DropdownColumn("library_type", "Library Type", 200, choices=LibraryType.names(), required=True),
        FloatColumn("seq_depth", "Sequencing Depth (M reads)", 200),
    ]

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=LibraryAnnotationForm._workflow_name,
            step_name=LibraryAnnotationForm._step_name, previous_form=previous_form,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=LibraryAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, form_type='raw', uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        duplicate_sample_libraries = df.duplicated(subset=["sample_name", "library_type"]) & df["library_type"].notna()
        
        seq_request_samples = db.get_seq_request_samples_df(self.seq_request.id)

        for i, (idx, row) in enumerate(df.iterrows()):
            if len(df[df["sample_name"] == row["sample_name"]]["genome"].unique()) > 1:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue("All libraries of a same sample must have the same genome"))
                self.spreadsheet.add_error(idx, "genome", InvalidCellValue("All libraries of a same sample must have the same genome"))

            if duplicate_sample_libraries.at[idx]:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("Duplicate 'Sample Name' and 'Library Type'"))

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                self.spreadsheet.add_error(idx, "library_type", DuplicateCellValue(f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request"))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def __map_library_types(self):
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        self.df["library_type_id"] = self.df["library_type"].map(library_type_map)

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
            "seq_depth": [],
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
                library_table_data["seq_depth"].append(row["seq_depth"])

                pooling_table["sample_name"].append(sample_name)
                pooling_table["library_name"].append(library_name)

        library_table = pd.DataFrame(library_table_data)

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
        
        if library_table["library_type_id"].isin([LibraryType.TENX_MULTIPLEXING_CAPTURE.id]).any():
            next_form = CMOAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif (library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif ((library_table["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id) | (library_table["library_type_id"] == LibraryType.TENX_SC_ABC_FLEX.id)).any():
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif LibraryType.TENX_SC_GEX_FLEX.id in library_table["library_type_id"].values:
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()

        