import pandas as pd
from flask import Response
from pandas.core.api import DataFrame as DataFrame

from opengsync_db import models
from opengsync_db.categories import IndexType, BarcodeOrientation

from .... import logger, db
from ..common import CommonTENXATACBarcodeInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .BarcodeMatchForm import BarcodeMatchForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm


class TENXATACBarcodeInputForm(CommonTENXATACBarcodeInputForm):
    _template_path = "workflows/library_annotation/sas-barcode-input.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(
        self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None
    ):
        CommonTENXATACBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=TENXATACBarcodeInputForm._workflow_name,
            formdata=formdata,
            pool=None, lab_prep=None, seq_request=seq_request,
        )

    def fill_previous_form(self):
        barcode_table = self.tables["tenx_atac_barcode_table"]
        self.spreadsheet.set_data(barcode_table)

    def get_barcode_table(self) -> DataFrame:
        data = {
            "library_name": [],
            "index_type_id": [],
            "index_well": [],
            "kit_i7_id": [],
            "kit_i5_id": [],
            "kit_i7": [],
            "kit_i5": [],
            "orientation_i7_id": [],
            "orientation_i5_id": [],
            "name_i7": [],
            "name_i5": [],
            "sequence_i7": [],
            "sequence_i5": [],
        }

        def add_barcode(
            library_name: str, index_type_id: int, index_well: str,
            kit_i7_id: int, kit_i5_id: int | None,
            kit_i7: str | None, kit_i5: str | None,
            orientation_i7_id: int | None, orientation_i5_id: int | None,
            name_i7: str, name_i5: str | None,
            sequence_i7: str, sequence_i5: str | None
        ):
            data["library_name"].append(library_name)
            data["index_type_id"].append(index_type_id)
            data["index_well"].append(index_well)
            data["kit_i7_id"].append(kit_i7_id)
            data["kit_i5_id"].append(kit_i5_id)
            data["orientation_i7_id"].append(orientation_i7_id)
            data["orientation_i5_id"].append(orientation_i5_id)
            data["name_i7"].append(name_i7)
            data["name_i5"].append(name_i5)
            data["kit_i7"].append(kit_i7)
            data["kit_i5"].append(kit_i5)
            data["sequence_i7"].append(sequence_i7)
            data["sequence_i5"].append(sequence_i5)

        if (barcode_table := self.tables.get("barcode_table")) is not None:
            for _, row in barcode_table.iterrows():
                add_barcode(
                    library_name=row["library_name"],
                    index_type_id=row["index_type_id"],
                    index_well=row["index_well"],
                    kit_i7_id=row["kit_i7_id"],
                    kit_i5_id=row["kit_i5_id"],
                    kit_i7=row["kit_i7"],
                    kit_i5=row["kit_i5"],
                    orientation_i7_id=row["orientation_i7_id"],
                    orientation_i5_id=row["orientation_i5_id"],
                    name_i7=row["name_i7"],
                    name_i5=row["name_i5"],
                    sequence_i7=row["sequence_i7"],
                    sequence_i5=row["sequence_i5"],
                )

        for _, row in self.df.iterrows():
            for i in range(1, 5):
                add_barcode(
                    library_name=row["library_name"],
                    index_type_id=IndexType.TENX_ATAC_INDEX.id,
                    index_well=row["index_well"],
                    kit_i7_id=row["kit_id"],
                    kit_i7=row["kit"],
                    orientation_i7_id=BarcodeOrientation.FORWARD.id if pd.notna(row["kit_id"]) else BarcodeOrientation.FORWARD_NOT_VALIDATED.id,
                    name_i7=row["name"],
                    sequence_i7=row[f"sequence_{i}"],
                    kit_i5=None,
                    kit_i5_id=None,
                    sequence_i5=None,
                    orientation_i5_id=None,
                    name_i5=None,
                )

        return DataFrame(data)

    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.metadata["index_col"] = self.index_col
        self.tables["tenx_atac_barcode_table"] = self.df
        barcode_table = self.get_barcode_table()
        self.tables["barcode_table"] = barcode_table
        self.step()

        if BarcodeMatchForm.is_applicable(self):
            next_form = BarcodeMatchForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseCRISPRGuideAnnotationForm.is_applicable(self):
            next_form = ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        return next_form.make_response()