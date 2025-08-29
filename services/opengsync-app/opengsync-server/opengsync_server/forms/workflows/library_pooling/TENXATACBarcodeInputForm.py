from flask import Response

from opengsync_db import models

from .... import logger, db  # noqa F401
from ....tools.spread_sheet_components import InvalidCellValue, IntegerColumn
from ..common import CommonTENXATACBarcodeInputForm
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm
from .BarcodeMatchForm import BarcodeMatchForm


class TENXATACBarcodeInputForm(CommonTENXATACBarcodeInputForm):
    _template_path = "workflows/library_pooling/barcode-input.html"
    _workflow_name = "library_pooling"
    lab_prep: models.LabPrep

    def __init__(
        self,
        lab_prep: models.LabPrep,
        formdata: dict | None,
        uuid: str | None
    ):
        CommonTENXATACBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=TENXATACBarcodeInputForm._workflow_name,
            formdata=formdata,
            pool=None, lab_prep=lab_prep, seq_request=None,
            additional_columns=[
                IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
            ]
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        for idx, row in self.df.iterrows():
            if row["library_id"] not in self.library_table["library_id"].values:
                self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
            else:
                try:
                    _id = int(row["library_id"])
                except ValueError:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                    continue
                if (library := db.libraries.get(_id)) is None:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                elif library.name != row["library_name"]:
                    self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))
                elif self.lab_prep is not None and library.lab_prep_id != self.lab_prep.id:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this lab prep"))
                elif self.seq_request is not None and library.seq_request_id != self.seq_request.id:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this sequencing request"))
                
                if self.library_table[self.library_table["library_id"] == row["library_id"]]["library_name"].isin([row["library_name"]]).all() == 0:
                    self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))

        return len(self.spreadsheet._errors) == 0
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.metadata["index_col"] = self.index_col
        barcode_table = self.get_barcode_table()
        self.add_table("tenx_atac_barcode_table", barcode_table)
        self.update_data()

        if BarcodeMatchForm.is_applicable(self):
            form = BarcodeMatchForm(lab_prep=self.lab_prep, uuid=self.uuid, formdata=None)
        else:
            form = CompleteLibraryPoolingForm(lab_prep=self.lab_prep, uuid=self.uuid, formdata=None)
        return form.make_response()