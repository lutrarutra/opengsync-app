from typing import Optional
from flask import Response

import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import BarcodeType, KitType, LibraryType, IndexType

from .... import db, logger
from ...MultiStepForm import MultiStepForm, StepFile
from ...SearchBar import SearchBar
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class IndexKitMappingForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-index_kit-mapping-form.html"
    _workflow_name = "library_annotation"
    _step_name = "index_kit_mapping"

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.tables["barcode_table"]["kit_i7"].notna().any()

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=IndexKitMappingForm._workflow_name,
            step_name=IndexKitMappingForm._step_name, previous_form=previous_form, step_args={}
        )

        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.library_table = self.tables["library_table"]
        self.barcode_table = self.tables["barcode_table"]

        if not formdata:
            index_kits = list(set(self.barcode_table["kit_i7"].unique().tolist() + self.barcode_table["kit_i5"].unique().tolist()))
            index_kits = [kit for kit in index_kits if pd.notna(kit)]

            for i, index_kit in enumerate(index_kits):
                if i > len(self.input_fields) - 1:
                    self.input_fields.append_entry()

                entry = self.input_fields[i]
                index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
                entry.raw_label.data = index_kit

                if index_kit is None:
                    selected_kit = None
                elif index_kit_search_field.selected.data is None:
                    selected_kit = next(iter(db.query_kits(str(index_kit), limit=1, kit_type=KitType.INDEX_KIT)), None)
                    index_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                    index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
                else:
                    selected_kit = db.get_index_kit(index_kit_search_field.selected.data)
                    index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None

    def fill_previous_form(self, previous_form: StepFile):
        self.barcode_table = previous_form.tables["barcode_table"]
        self.library_table = previous_form.tables["library_table"]

        kits = set()

        counter = 0
        for (label, kit_name, kit_id), _ in self.barcode_table.groupby(["kit_i7", "kit_i7_name", "kit_i7_id"]):
            if label in kits:
                continue
            kits.add(label)
            if counter > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry: IndexKitSubForm = self.input_fields[counter]  # type: ignore
            entry.raw_label.data = label
            entry.index_kit.selected.data = kit_id
            entry.index_kit.search_bar.data = kit_name
            counter += 1

        for (label, kit_name, kit_id), _ in self.barcode_table.groupby(["kit_i5", "kit_i5_name", "kit_i5_id"]):
            if label in kits:
                continue
            kits.add(label)
            if counter > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry: IndexKitSubForm = self.input_fields[counter]  # type: ignore
            entry.raw_label.data = label
            entry.index_kit.selected.data = kit_id
            entry.index_kit.search_bar.data = kit_name
            counter += 1

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        kits: dict[int, tuple[models.IndexKit, pd.DataFrame]] = {}

        for i, entry in enumerate(self.input_fields):
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
            if (kit_id := index_kit_search_field.selected.data) is None:
                logger.error(f"Index kit not found for {entry.raw_label.data}")
                raise Exception()
            
            if (kit := db.get_index_kit(kit_id)) is None:
                index_kit_search_field.selected.errors = (f"Index kit {kit_id} not found",)
                return False

            if len(kit_df := db.get_index_kit_barcodes_df(kit_id, per_adapter=False)) == 0:
                logger.error(f"Index kit {kit_id} does not exist")
                raise Exception()
            
            kits[kit_id] = (kit, kit_df)
            self.barcode_table.loc[self.barcode_table["kit_i7"] == entry.raw_label.data, "kit_i7_id"] = kit_id
            self.barcode_table.loc[self.barcode_table["kit_i5"] == entry.raw_label.data, "kit_i5_id"] = kit_id
            self.barcode_table.loc[self.barcode_table["kit_i7_id"] == kit_id, "kit_i7_name"] = kit.search_name()
            self.barcode_table.loc[self.barcode_table["kit_i5_id"] == kit_id, "kit_i5_name"] = kit.search_name()

            for _, row in self.barcode_table[self.barcode_table["kit_i7_id"] == kit_id].iterrows():
                if pd.notna(row["name_i7"]):
                    if row["name_i7"] not in kit_df["name"].values:
                        index_kit_search_field.selected.errors = (f"Index {row['name_i7']} not found in index kit {kit_id}",)
                        return False
                
                elif pd.notna(row["index_well"]):
                    if row["index_well"] not in kit_df["well"].values:
                        index_kit_search_field.selected.errors = (f"Well {row['index_well']} not found in index kit {kit_id}",)
                        return False
                    
            for _, row in self.barcode_table[self.barcode_table["kit_i5_id"] == kit_id].iterrows():
                if pd.notna(row["name_i5"]):
                    if row["name_i5"] not in kit_df["name"].values:
                        index_kit_search_field.selected.errors = (f"Index {row['name_i5']} not found in index kit {kit_id}",)
                        return False
                
                elif pd.notna(row["index_well"]):
                    if row["index_well"] not in kit_df["well"].values:
                        index_kit_search_field.selected.errors = (f"Well {row['index_well']} not found in index kit {kit_id}",)
                        return False

        index_kits = list(set(self.barcode_table["kit_i7_id"].unique().tolist() + self.barcode_table["kit_i5_id"].unique().tolist()))
        index_kits = [kit for kit in index_kits if pd.notna(kit)]

        kit_defined = self.barcode_table["kit_i7"].notna() | self.barcode_table["kit_i5"].notna()

        barcode_table_data = {
            "library_name": [],
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
            "kit_i7_id": [],
            "kit_i5_id": [],
            "kit_i7_name": [],
            "kit_i5_name": [],
        }

        for idx, row in self.barcode_table.iterrows():
            if kit_defined.at[idx]:
                kit_i7, kit_i7_df = kits[row["kit_i7_id"]]
                kit_i5, kit_i5_df = kits[row["kit_i5_id"]]

                i7_seqs = kit_i7_df.loc[kit_i7_df["type_id"] == BarcodeType.INDEX_I7.id]
                i5_seqs = kit_i5_df.loc[kit_i5_df["type_id"] == BarcodeType.INDEX_I5.id]

                if pd.notna(row["name_i7"]):
                    barcodes_i7 = i7_seqs[i7_seqs["name"] == row["name_i7"]]["sequence"].values
                    names_i7 = i7_seqs[i7_seqs["name"] == row["name_i7"]]["name"].values
                elif pd.notna(row["index_well"]):
                    barcodes_i7 = i7_seqs[i7_seqs["well"] == row["index_well"]]["sequence"].values
                    names_i7 = i7_seqs[i7_seqs["well"] == row["index_well"]]["name"].values
                else:
                    raise ValueError()
                
                if pd.notna(row["name_i5"]):
                    barcodes_i5 = i5_seqs[i5_seqs["name"] == row["name_i5"]]["sequence"].values
                    names_i5 = i5_seqs[i5_seqs["name"] == row["name_i5"]]["name"].values
                elif pd.notna(row["index_well"]):
                    barcodes_i5 = i5_seqs[i5_seqs["well"] == row["index_well"]]["sequence"].values
                    names_i5 = i5_seqs[i5_seqs["well"] == row["index_well"]]["name"].values
                else:
                    raise ValueError()
                
                for i in range(max(len(barcodes_i7), len(barcodes_i5))):
                    barcode_table_data["library_name"].append(row["library_name"])
                    barcode_table_data["index_well"].append(row["index_well"])
                    barcode_table_data["kit_i7"].append(row["kit_i7"])
                    barcode_table_data["kit_i5"].append(row["kit_i5"])
                    barcode_table_data["kit_i7_id"].append(row["kit_i7_id"])
                    barcode_table_data["kit_i5_id"].append(row["kit_i5_id"])
                    barcode_table_data["kit_i7_name"].append(kit_i7.search_name())
                    barcode_table_data["kit_i5_name"].append(kit_i5.search_name())
                    barcode_table_data["sequence_i7"].append(barcodes_i7[i] if len(barcodes_i7) > i else None)
                    barcode_table_data["sequence_i5"].append(barcodes_i5[i] if len(barcodes_i5) > i else None)
                    barcode_table_data["name_i7"].append(names_i7[i] if len(names_i7) > i else None)
                    barcode_table_data["name_i5"].append(names_i5[i] if len(names_i5) > i else None)
            else:
                barcode_table_data["library_name"].append(row["library_name"])
                barcode_table_data["index_well"].append(row["index_well"])
                barcode_table_data["kit_i7"].append(None)
                barcode_table_data["kit_i5"].append(None)
                barcode_table_data["kit_i7_id"].append(None)
                barcode_table_data["kit_i5_id"].append(None)
                barcode_table_data["kit_i7_name"].append(None)
                barcode_table_data["kit_i5_name"].append(None)
                barcode_table_data["sequence_i7"].append(row["sequence_i7"])
                barcode_table_data["sequence_i5"].append(row["sequence_i5"])
                barcode_table_data["name_i7"].append(row["name_i7"])
                barcode_table_data["name_i5"].append(row["name_i5"])
 
        self.barcode_table = pd.DataFrame(barcode_table_data)
        return True
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.barcode_table["index_type_id"] = None
        self.barcode_table.loc[(self.barcode_table["sequence_i7"].notna() & self.barcode_table["sequence_i5"].notna()), "index_type_id"] = IndexType.DUAL_INDEX.id
        self.barcode_table.loc[(self.barcode_table["sequence_i7"].notna() & self.barcode_table["sequence_i5"].isna()), "index_type_id"] = IndexType.SINGLE_INDEX.id
        for (library_name, library_type_id), _ in self.library_table.groupby(["library_name", "library_type_id"]):
            if LibraryType.get(library_type_id) == LibraryType.TENX_SC_ATAC:
                self.barcode_table.loc[self.barcode_table["library_name"] == library_name, "index_type_id"] = IndexType.TENX_ATAC_INDEX.id

        self.update_table("barcode_table", self.barcode_table)
        self.update_data()
        if OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()