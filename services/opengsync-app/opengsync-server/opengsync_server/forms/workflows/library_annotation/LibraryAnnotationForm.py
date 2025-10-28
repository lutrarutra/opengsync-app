import pandas as pd

from flask import Response, url_for
from wtforms import BooleanField

from opengsync_db import models
from opengsync_db.categories import LibraryType, GenomeRef

from .... import logger, db
from ....tools import utils
from ....tools.spread_sheet_components import InvalidCellValue, DuplicateCellValue, TextColumn, FloatColumn, CategoricalDropDown
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class LibraryAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-library_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "library_annotation"

    nuclei_isolation = BooleanField("Nuclei Isolation", default=False, description="I want you to isolate nuclei from my samples before sequencing.")

    columns = [
        TextColumn("sample_name", "Sample Name", 200, required=True, max_length=models.Sample.name.type.length, min_length=4, validation_fnc=utils.check_string),
        CategoricalDropDown("genome_id", "Genome", 200, categories=dict(GenomeRef.as_selectable()), required=True),
        CategoricalDropDown("library_type_id", "Library Type", 200, categories=dict(LibraryType.as_selectable()), required=True),
        FloatColumn("seq_depth", "Sequencing Depth (M reads)", 200),
    ]

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=LibraryAnnotationForm._workflow_name,
            step_name=LibraryAnnotationForm._step_name,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=LibraryAnnotationForm.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, form_type='raw', uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df
        df["library_type"] = df["library_type_id"].apply(lambda x: LibraryType.get(int(x)).display_name if pd.notna(x) else None)
        df["genome"] = df["genome_id"].apply(lambda x: GenomeRef.get(int(x)).display_name if pd.notna(x) else None)
        
        duplicate_sample_libraries = df.duplicated(subset=["sample_name", "library_type"]) & df["library_type"].notna()
        seq_request_samples = db.pd.get_seq_request_samples(self.seq_request.id)

        for idx, row in df.iterrows():
            if len(df[df["sample_name"] == row["sample_name"]]["genome"].unique()) > 1:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue("All libraries of a same sample must have the same genome"))
                self.spreadsheet.add_error(idx, "genome", InvalidCellValue("All libraries of a same sample must have the same genome"))

            if duplicate_sample_libraries.at[idx]:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("Duplicate 'Sample Name' and 'Library Type'"))

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                self.spreadsheet.add_error(idx, "library_type_id", DuplicateCellValue(f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request"))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def fill_previous_form(self, previous_form: StepFile):
        self.spreadsheet.set_data(previous_form.tables["library_table"])

    def __map_existing_samples(self):
        self.df["sample_id"] = None
        if self.metadata["project_id"] is None:
            return
        if (project := db.projects.get(self.metadata["project_id"])) is None:
            logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
            raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
        
        for sample in project.samples:
            self.df.loc[self.df["sample_name"] == sample.name, "sample_id"] = sample.id

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.__map_existing_samples()

        self.metadata["nuclei_isolation"] = self.nuclei_isolation.data
        self.metadata["mux_type_id"] = None

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

        sample_pooling_table = {
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

                sample_pooling_table["sample_name"].append(sample_name)
                sample_pooling_table["library_name"].append(library_name)

        library_table = pd.DataFrame(library_table_data)

        sample_table = pd.DataFrame(sample_table_data)
        sample_table["sample_id"] = None

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.projects.get(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        sample_pooling_table = pd.DataFrame(sample_pooling_table)
        sample_pooling_table["mux_type_id"] = None

        self.add_table("library_table", library_table)
        self.add_table("sample_table", sample_table)
        self.add_table("sample_pooling_table", sample_pooling_table)
        self.update_data()
        
        if OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        if OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()

        