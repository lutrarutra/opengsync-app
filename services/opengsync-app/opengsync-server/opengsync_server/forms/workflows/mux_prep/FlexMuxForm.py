from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, MUXType

from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, DuplicateCellValue, IntegerColumn
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .FlexABCForm import FlexABCForm


class FlexMuxForm(MultiStepForm):
    _template_path = "workflows/mux_prep/mux_prep-flex_annotation.html"
    _workflow_name = "mux_prep"
    _step_name = "flex_mux_annotation"
    
    columns = [
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Sample Pool", 300, required=True, max_length=models.Sample.name.type.length, clean_up_fnc=tools.make_alpha_numeric),
        TextColumn("barcode_id", "Bardcode ID", 200, required=True, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=lambda x: str(x).strip().upper()),
    ]

    allowed_barcodes = [f"BC{i:03}" for i in range(1, 17)]
    mux_type = MUXType.TENX_FLEX_PROBE

    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None, uuid: Optional[str] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexMuxForm._workflow_name,
            step_name=FlexMuxForm._step_name, step_args={"mux_type_id": FlexMuxForm.mux_type.id}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        self.sample_table = db.get_lab_prep_samples_df(lab_prep.id)
        self.gex_table = self.sample_table[
            (self.sample_table["mux_type"].isin([MUXType.TENX_FLEX_PROBE])) &
            (self.sample_table["library_type"].isin([LibraryType.TENX_SC_GEX_FLEX]))
        ].copy()

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for("mux_prep_workflow.parse_flex_annotation", lab_prep_id=self.lab_prep.id, uuid=self.uuid),
            formdata=formdata
        )

    def prepare(self):
        df = self.gex_table.copy()
        df["barcode_id"] = df["mux"].apply(lambda x: x.get("barcode"))
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        def padded_barcode_id(s: str) -> str:
            number = ''.join(filter(str.isdigit, s))
            return f"BC{number.zfill(3)}"
        
        df["barcode_id"] = df["barcode_id"].apply(lambda s: padded_barcode_id(s) if pd.notna(s) else None)

        duplicate_barcode = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)
        
        for i, (idx, row) in enumerate(df.iterrows()):
            if row["sample_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", InvalidCellValue(f"Unknown sample '{row['sample_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}"))

            if row["barcode_id"] not in FlexMuxForm.allowed_barcodes:
                self.spreadsheet.add_error(idx, "barcode_id", InvalidCellValue(f"'Barcode ID' must be one of: {', '.join(FlexMuxForm.allowed_barcodes)}"))
            elif duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."))

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.gex_table["new_sample_pool"] = utils.map_columns(self.gex_table, self.df, ["sample_name", "library_id"], "sample_pool")
        self.gex_table["mux_barcode"] = utils.map_columns(self.gex_table, self.df, ["sample_name", "library_id"], "barcode_id")

        self.add_table("sample_table", self.sample_table)
        self.add_table("gex_table", self.gex_table)
        if FlexABCForm.is_applicable(self):
            self.update_data()
            form = FlexABCForm(lab_prep=self.lab_prep, uuid=self.uuid)
            return form.make_response()

        FlexABCForm.make_sample_pools(
            sample_table=self.gex_table,
            lab_prep=self.lab_prep
        )

        self.complete()
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id)))