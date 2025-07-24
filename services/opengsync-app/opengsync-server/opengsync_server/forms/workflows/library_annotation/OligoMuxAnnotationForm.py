from typing import Optional

import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, FeatureType, MUXType

from .... import logger, tools, db  # noqa
from ....tools.spread_sheet_components import TextColumn, DropdownColumn, MissingCellValue, InvalidCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm, StepFile
from ...SpreadsheetInput import SpreadsheetInput
from .KitMappingForm import KitMappingForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class OligoMuxAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-oligo_mux_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "oligo_mux_annotation"
    columns = [
        TextColumn("demux_name", "Demultiplexed Name", 170, required=True, max_length=models.Sample.name.type.length, min_length=4, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        DropdownColumn("sample_name", "Sample (Pool) Name", 170, choices=[], required=True),
        TextColumn("kit", "Kit", 170, max_length=models.Kit.name.type.length),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, min_length=4, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        DropdownColumn("read", "Read", 100, choices=["", "R2", "R1"]),
    ]

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.tables["library_table"]["library_type_id"].isin([LibraryType.TENX_MUX_OLIGO.id]).any()

    @classmethod
    def __get_multiplexed_samples(cls, df: pd.DataFrame) -> list[str]:
        multiplexed_samples = set()
        for sample_name, _df in df.groupby("sample_name"):
            if LibraryType.TENX_MUX_OLIGO.id in _df["library_type_id"].unique():
                multiplexed_samples.add(sample_name)
        return list(multiplexed_samples)

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=OligoMuxAnnotationForm._workflow_name, step_name=OligoMuxAnnotationForm._step_name,
            uuid=uuid, formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.upload_path = "uploads/seq_request"

        self.multiplexed_samples = OligoMuxAnnotationForm.__get_multiplexed_samples(self.tables["library_table"])

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=OligoMuxAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_cmo_reference', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )
        self.spreadsheet.columns["sample_name"].source = self.multiplexed_samples

    def fill_previous_form(self, previous_form: StepFile):
        self.spreadsheet.set_data(previous_form.tables["sample_pooling_table"])

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        kit_feature = pd.notna(df["kit"]) & pd.notna(df["feature"])
        custom_feature = pd.notna(df["sequence"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
        invalid_feature = (pd.notna(df["kit"]) | pd.notna(df["feature"])) & (pd.notna(df["sequence"]) | pd.notna(df["pattern"]) | pd.notna(df["read"]))
        duplicate_oligo = (
            (df.duplicated(subset=["sample_name", "sequence", "pattern", "read"], keep=False) & custom_feature) |
            (df.duplicated(subset=["sample_name", "kit", "feature"], keep=False) & kit_feature)
        )

        for i, (idx, row) in enumerate(df.iterrows()):
            # Not defined custom nor kit feature
            if (not custom_feature.at[idx] and not kit_feature.at[idx]):
                self.spreadsheet.add_error(idx, "kit", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "feature", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "sequence", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                self.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

            # Defined both custom and kit feature
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

            elif invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

            if duplicate_oligo.at[idx]:
                self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "read", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "kit", DuplicateCellValue("Definitions must be unique for each sample."))
                self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Definitions must be unique for each sample."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        self.df["custom_feature"] = custom_feature
        self.df["kit_feature"] = kit_feature

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_table = self.tables["sample_table"]
        sample_pooling_table = self.tables["sample_pooling_table"]

        sample_data = {"sample_name": []}

        pooling_data = {
            "sample_name": [],
            "library_name": [],
            "mux_barcode": [],
            "mux_pattern": [],
            "mux_read": [],
            "kit": [],
            "feature": [],
            "mux_type_id": [],
            "sample_pool": [],
        }

        for _, mux_row in self.df.iterrows():
            sample_data["sample_name"].append(mux_row["demux_name"])
            for _, pooling_row in sample_pooling_table[sample_pooling_table["sample_name"] == mux_row["sample_name"]].iterrows():
                pooling_data["sample_name"].append(mux_row["demux_name"])
                pooling_data["library_name"].append(pooling_row["library_name"])
                pooling_data["mux_barcode"].append(mux_row["sequence"] if mux_row["custom_feature"] else None)
                pooling_data["mux_pattern"].append(mux_row["pattern"] if mux_row["custom_feature"] else None)
                pooling_data["mux_read"].append(mux_row["read"] if mux_row["custom_feature"] else None)
                pooling_data["kit"].append(mux_row["kit"] if mux_row["kit_feature"] else None)
                pooling_data["feature"].append(mux_row["feature"] if mux_row["kit_feature"] else None)
                pooling_data["mux_type_id"].append(MUXType.TENX_OLIGO.id)
                pooling_data["sample_pool"].append(mux_row["sample_name"])
        
        sample_pooling_table = pd.DataFrame(pooling_data)
        self.update_table("sample_pooling_table", sample_pooling_table, update_data=False)

        sample_table = pd.DataFrame(sample_data)
        sample_table["sample_id"] = None
        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.get_project(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        self.update_table("sample_table", sample_table, update_data=False)
                
        kit_table = self.df[self.df["kit"].notna()][["kit"]].drop_duplicates().copy()
        kit_table["type_id"] = FeatureType.CMO.id
        kit_table["kit_id"] = None

        if kit_table.shape[0] > 0:
            if (existing_kit_table := self.tables.get("kit_table")) is None:  # type: ignore
                self.add_table("kit_table", kit_table)
            else:
                kit_table = pd.concat([kit_table[kit_table["type_id"] != FeatureType.CMO.id], existing_kit_table])
                self.update_table("kit_table", kit_table, update_data=False)
        
        self.update_data()

        if FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif KitMappingForm.is_applicable(self):
            next_form = KitMappingForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)

        return next_form.make_response()