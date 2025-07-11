from typing import Optional

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType, IndexType

from .... import logger, tools, db  # noqa F401
from ...MultiStepForm import MultiStepForm, StepFile

from ....tools.spread_sheet_components import TextColumn, DropdownColumn, InvalidCellValue
from ...SpreadsheetInput import SpreadsheetInput
from .IndexKitMappingForm import IndexKitMappingForm
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .BarcodeMatchForm import BarcodeMatchForm
from .OCMAnnotationForm import OCMAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class BarcodeInputForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-barcode-input.html"
    _workflow_name = "library_annotation"
    _step_name = "barcode_input"
    
    columns = [
        DropdownColumn("library_name", "Library Name", 250, choices=[], required=True),
        TextColumn("index_well", "Index Well", 100, max_length=8),
        TextColumn("kit_i7", "i7 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_i7", "i7 Sequence", 180, max_length=models.LibraryIndex.sequence_i7.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with="")),
        TextColumn("kit_i5", "i5 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
        TextColumn("sequence_i5", "i5 Sequence", 180, max_length=models.LibraryIndex.sequence_i7.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with="")),
    ]

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=BarcodeInputForm._workflow_name,
            step_name=BarcodeInputForm._step_name, previous_form=previous_form,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.library_table = self.tables["library_table"]
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=BarcodeInputForm.columns, csrf_token=csrf_token,
            post_url=url_for("library_annotation_workflow.parse_barcode_table", seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, df=self.get_template(),
        )

        self.spreadsheet.columns["library_name"].source = self.library_table["library_name"].unique().tolist()

    def fill_previous_form(self, previous_form: StepFile):
        self.spreadsheet.set_data(previous_form.tables["barcode_table"])

    def get_template(self) -> pd.DataFrame:
        barcode_table_data = {
            "library_name": [],
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
        }

        for _, row in self.library_table.iterrows():
            barcode_table_data["library_name"].append(row["library_name"])
            barcode_table_data["index_well"].append(None)
            barcode_table_data["kit_i7"].append(None)
            barcode_table_data["name_i7"].append(None)
            barcode_table_data["sequence_i7"].append(None)
            barcode_table_data["kit_i5"].append(None)
            barcode_table_data["name_i5"].append(None)
            barcode_table_data["sequence_i5"].append(None)
        
        return pd.DataFrame(barcode_table_data)
    
    def validate(self) -> bool:
        validated = super().validate()
            
        if not validated:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        df.loc[df["kit_i7"].notna(), "kit_i7"] = df.loc[df["kit_i7"].notna(), "kit_i7"].astype(str)
        df.loc[df["kit_i5"].notna(), "kit_i5"] = df.loc[df["kit_i5"].notna(), "kit_i5"].astype(str)
            
        df["sequence_i7"] = df["sequence_i7"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))
        df["sequence_i5"] = df["sequence_i5"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))

        df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = df["kit_i7"].notna() & (df["index_well"].notna() | df["name_i7"].notna())
        manual_defined = df["sequence_i7"].notna()

        df.loc[df["kit_i5"].isna(), "kit_i5"] = df.loc[df["kit_i5"].isna(), "kit_i7"]
        df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        for name in self.library_table["library_name"].values:
            if name not in df["library_name"].values:
                self.spreadsheet.add_general_error(f"Missing '{name}'")

        for i, (idx, row) in enumerate(df.iterrows()):
            if row["library_name"] not in self.library_table["library_name"].values:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

            if not kit_defined.at[idx] and not manual_defined.at[idx]:
                self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))

        validated = validated and (len(self.spreadsheet._errors) == 0)

        self.df = df

        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        barcode_table_data = {
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
            "library_name": [],
        }
        
        for idx, row in self.df.iterrows():
            index_i7_seqs = row["sequence_i7"].split(";") if pd.notna(row["sequence_i7"]) else [None]
            index_i5_seqs = row["sequence_i5"].split(";") if pd.notna(row["sequence_i5"]) else [None]

            for i in range(max(len(index_i7_seqs), len(index_i5_seqs))):
                barcode_table_data["library_name"].append(row["library_name"])
                barcode_table_data["index_well"].append(row["index_well"])
                barcode_table_data["kit_i7"].append(row["kit_i7"])
                barcode_table_data["name_i7"].append(row["name_i7"])
                barcode_table_data["sequence_i7"].append(index_i7_seqs[i] if len(index_i7_seqs) > i else None)
                barcode_table_data["kit_i5"].append(row["kit_i5"])
                barcode_table_data["name_i5"].append(row["name_i5"])
                barcode_table_data["sequence_i5"].append(index_i5_seqs[i] if len(index_i5_seqs) > i else None)

        barcode_table = pd.DataFrame(barcode_table_data)
        barcode_table["kit_i7_id"] = None
        barcode_table["kit_i7_name"] = None
        barcode_table["kit_i5_id"] = None
        barcode_table["kit_i5_name"] = None
        barcode_table["index_type_id"] = None

        barcode_table.loc[(barcode_table["sequence_i7"].notna() & barcode_table["sequence_i5"].notna()), "index_type_id"] = IndexType.DUAL_INDEX.id
        barcode_table.loc[(barcode_table["sequence_i7"].notna() & barcode_table["sequence_i5"].isna()), "index_type_id"] = IndexType.SINGLE_INDEX.id
        for (library_name, library_type_id), _ in self.library_table.groupby(["library_name", "library_type_id"]):
            if LibraryType.get(library_type_id) == LibraryType.TENX_SC_ATAC:
                barcode_table.loc[barcode_table["library_name"] == library_name, "index_type_id"] = IndexType.TENX_ATAC_INDEX.id

        self.add_table("barcode_table", barcode_table)
        self.update_data()

        if BarcodeMatchForm.is_applicable(self):
            next_form = BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid, previous_form=self)
        elif IndexKitMappingForm.is_applicable(self):
            next_form = IndexKitMappingForm(seq_request=self.seq_request, uuid=self.uuid, previous_form=self)
        elif OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()