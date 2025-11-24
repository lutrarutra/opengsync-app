import os
import pandas as pd
from flask import url_for, Response

from opengsync_db import models

from .... import logger, db  # noqa F401
from ....core import runtime
from ....tools.spread_sheet_components import TextColumn, IntegerColumn, InvalidCellValue
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm


class LibraryPoolingForm(MultiStepForm):
    _template_path = "workflows/library_pooling/library_pooling.html"
    _workflow_name = "library_pooling"
    _step_name = "library_pooling"

    columns: list = [
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("library_name", "Library Name", 300, required=True, read_only=True),
        TextColumn("pool", "Pool", 300, required=True),
    ]

    def __init__(
        self,
        lab_prep: models.LabPrep,
        formdata: dict | None,
        uuid: str | None
    ):
        MultiStepForm.__init__(
            self, workflow=CompleteLibraryPoolingForm._workflow_name,
            step_name=CompleteLibraryPoolingForm._step_name, uuid=uuid,
            formdata=formdata, step_args={}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep

        self.library_table = db.pd.get_lab_prep_libraries(lab_prep_id=lab_prep.id)

        if self.library_table["pool"].isna().any():
            if self.lab_prep.prep_file is not None:
                prep_table = pd.read_excel(os.path.join(runtime.app.media_folder, self.lab_prep.prep_file.path), "prep_table")  # type: ignore
                prep_table = prep_table.dropna(subset=["library_id", "library_name"])
                for idx, row in self.library_table[self.library_table["pool"].isna()].iterrows():
                    self.library_table.at[idx, "pool"] = next(iter(prep_table[  # type: ignore
                        (prep_table["library_id"] == row["library_id"])
                    ]["pool"].values.tolist()), None)

        self.post_url = url_for("library_pooling_workflow.upload_pooling_form", uuid=self.uuid, lab_prep_id=self.lab_prep.id)
        self.library_table.loc[self.library_table["pool"].notna(), "pool"] = self.library_table.loc[self.library_table["pool"].notna(), "pool"].astype(str).str.strip().str.removeprefix(f"{self.lab_prep.name}_")

        self.spreadsheet = SpreadsheetInput(
            columns=LibraryPoolingForm.columns,
            csrf_token=self._csrf_token,
            post_url=self.post_url, formdata=formdata, df=self.library_table
        )
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        if self.df.loc[~self.df["pool"].astype(str).str.strip().str.lower().isin(["x", "t", "skip"]), "pool"].isna().all():
            self.df.loc[self.df["pool"].isna(), "pool"] = "1"

        for idx, row in self.df.iterrows():
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
                    if (library := db.libraries.get(_id)) is None:
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
        
        self.add_table("pooling_table", self.df)
        self.add_table("library_table", self.library_table)
        self.update_data()

        form = CompleteLibraryPoolingForm(lab_prep=self.lab_prep, uuid=self.uuid, formdata=None)
        return form.make_response()