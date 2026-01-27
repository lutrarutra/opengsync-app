from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, MUXType

from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, IntegerColumn
from ...MultiStepForm import MultiStepForm
from ..common import CommonFlexABCForm, CommonFlexMuxForm


class FlexABCForm(CommonFlexABCForm):
    _template_path = "workflows/mux_prep/mux_prep-flex_abc_annotation.html"
    _workflow_name = "mux_prep"
    abc_table: pd.DataFrame
    gex_table: pd.DataFrame
    sample_table: pd.DataFrame
    lab_prep: models.LabPrep
    df: pd.DataFrame

    @staticmethod
    def padded_barcode_id(s: int | str | None) -> str | None:
        if pd.isna(s):
            return None
        number = ''.join(filter(str.isdigit, str(s)))
        return f"AB{number.zfill(3)}"
    
    columns = [
        IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("sample_pool", "Sample Pool", 300, required=True, read_only=True),
        TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=padded_barcode_id),
    ]

    allowed_barcodes = [f"AB{i:03}" for i in range(1, 17)]
    mux_type = MUXType.TENX_FLEX_PROBE

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        sample_table = current_step.tables["sample_table"]
        return LibraryType.TENX_SC_ABC_FLEX in sample_table["library_type"].values

    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None, uuid: Optional[str] = None):
        CommonFlexABCForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexABCForm._workflow_name,
            lab_prep=lab_prep, seq_request=None, library=None, columns=FlexABCForm.columns
        )

    def prepare(self):
        df = self.abc_table
        df["gex_barcode"] = utils.map_columns(df, self.gex_table, "sample_name", "mux_barcode")
        df["barcode_id"] = df["mux"].apply(lambda x: x.get("barcode") if pd.notna(x) and isinstance(x, dict) else None)
        df.loc[df["barcode_id"].isna(), "barcode_id"] = df.loc[df["barcode_id"].isna(), "gex_barcode"].apply(
            lambda x: x.replace("BC", "AB") if pd.notna(x) else None
        )
        df = df.drop(columns=["gex_barcode"])
        self.spreadsheet.set_data(df)

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.abc_table["mux_barcode"] = utils.map_columns(self.abc_table, self.df, ["sample_name", "library_id"], "barcode_id")
        sample_table = pd.concat([self.abc_table, self.gex_table], ignore_index=True).reset_index(drop=True)

        CommonFlexMuxForm.update_barcodes(sample_table)
        
        self.complete()
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id, tab="mux-tab")))