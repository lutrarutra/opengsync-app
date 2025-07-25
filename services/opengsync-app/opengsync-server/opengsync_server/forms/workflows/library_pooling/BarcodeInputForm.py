import pandas as pd

from flask import Response

from opengsync_db import models

from .... import logger, db  # noqa F401
from ....tools.spread_sheet_components import IntegerColumn, TextColumn, DropdownColumn, InvalidCellValue
from ...MultiStepForm import MultiStepForm
from ..common import CommonBarcodeInputForm
from .IndexKitMappingForm import IndexKitMappingForm
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm


class BarcodeInputForm(CommonBarcodeInputForm):
    _template_path = "workflows/library_pooling/barcode-input.html"
    _workflow_name = "library_pooling"
    lab_prep: models.LabPrep

    def __init__(
        self,
        lab_prep: models.LabPrep,
        formdata: dict | None,
        uuid: str | None
    ):
        CommonBarcodeInputForm.__init__(
            self, uuid=uuid, workflow=BarcodeInputForm._workflow_name,
            formdata=formdata,
            pool=None, lab_prep=lab_prep, seq_request=None,
            additional_columns=[
                IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
                DropdownColumn("library_name", "Library Name", 250, choices=[], required=True, read_only=True),
                TextColumn("pool", "Pool", 100, required=False, max_length=models.Pool.name.type.length),
            ]
        )
    
    def fill_previous_form(self, previous_form: MultiStepForm):
        self.spreadsheet.set_data(previous_form.tables["library_table"])
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False

        if self.df.loc[~self.df["pool"].astype(str).str.strip().str.lower().isin(["x", "t"]), "pool"].isna().all():
            self.df.loc[self.df["pool"].isna(), "pool"] = "1"

        for i, (idx, row) in enumerate(self.df.iterrows()):
            if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "x":
                continue
            if pd.notna(row["pool"]) and str(row["pool"]).strip().lower() == "t":
                if row["library_id"]:
                    self.spreadsheet.add_error(idx, "pool", InvalidCellValue("Requested library cannot be marked as control"))
                else:
                    continue

            if row["library_id"] not in self.library_table["library_id"].values:
                self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
            else:
                try:
                    _id = int(row["library_id"])
                except ValueError:
                    self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                    _id = None

                if _id is not None:
                    if (library := db.get_library(_id)) is None:
                        self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("invalid 'library_id'"))
                    elif library.name != row["library_name"]:
                        self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))
                    elif library.lab_prep_id != self.lab_prep.id:
                        self.spreadsheet.add_error(idx, "library_id", InvalidCellValue("Library is not part of this lab prep"))

            if self.library_table[self.library_table["library_id"] == row["library_id"]]["library_name"].isin([row["library_name"]]).all() == 0:
                self.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name' for 'library_id'"))

        return len(self.spreadsheet._errors) == 0

    def process_request(self) -> Response:
        if not self.validate():
            self._context["active_tab"] = "spreadsheet"
            return self.make_response()
        
        barcode_table = self.get_barcode_table()
        
        self.metadata["lab_prep_id"] = self.lab_prep.id
        self.add_table("barcode_table", barcode_table)
        self.add_table("library_table", self.df)
        self.update_data()

        if IndexKitMappingForm.is_applicable(self):
            form = IndexKitMappingForm(lab_prep=self.lab_prep, uuid=self.uuid, formdata=None)
            return form.make_response()

        form = CompleteLibraryPoolingForm(lab_prep=self.lab_prep, uuid=self.uuid)
        return form.make_response()