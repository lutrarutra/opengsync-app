from flask import Response

from opengsync_db import models

from .... import logger, db  # noqa F401
from ....tools.spread_sheet_components import InvalidCellValue, IntegerColumn
from .TENXATACBarcodeInputForm import TENXATACBarcodeInputForm
from ..common import CommonBarcodeInputForm
from .CompleteReindexForm import CompleteReindexForm
from .BarcodeMatchForm import BarcodeMatchForm


class BarcodeInputForm(CommonBarcodeInputForm):
    _template_path = "workflows/reindex/barcode-input.html"
    _workflow_name = "reindex"

    def __init__(
        self,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None,
        uuid: str | None
    ):
        CommonBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=BarcodeInputForm._workflow_name,
            formdata=formdata,
            pool=pool, lab_prep=lab_prep, seq_request=seq_request,
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
        
        barcode_table = self.df
        self.metadata["index_col"] = self.index_col
        self.add_table("library_table", self.library_table)
        self.add_table("barcode_table", barcode_table)
        self.update_data()

        if TENXATACBarcodeInputForm.is_applicable(self):
            form = TENXATACBarcodeInputForm(uuid=self.uuid, lab_prep=self.lab_prep, seq_request=self.seq_request, pool=self.pool, formdata=None)
        elif BarcodeMatchForm.is_applicable(self):
            form = BarcodeMatchForm(seq_request=self.seq_request, lab_prep=self.lab_prep, pool=self.pool, uuid=self.uuid, formdata=None)
        else:
            form = CompleteReindexForm(seq_request=self.seq_request, lab_prep=self.lab_prep, pool=self.pool, uuid=self.uuid, formdata=None)
        return form.make_response()
        
