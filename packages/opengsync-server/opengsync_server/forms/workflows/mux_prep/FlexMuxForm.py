import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models

from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, DuplicateCellValue, IntegerColumn
from ..common.CommonFlexMuxForm import CommonFlexMuxForm
from .FlexABCForm import FlexABCForm


class FlexMuxForm(CommonFlexMuxForm):
    _template_path = "workflows/mux_prep/mux_prep-flex_annotation.html"
    _workflow_name = "mux_prep"
    lab_prep: models.LabPrep

    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None, uuid: str | None = None):
        CommonFlexMuxForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexMuxForm._workflow_name,
            seq_request=None, library=None, lab_prep=lab_prep, columns=[
                IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
                IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
                TextColumn("sample_pool", "Sample Pool", 300, required=True, read_only=True),
                TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
                TextColumn("barcode_id", "Bardcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=CommonFlexMuxForm.padded_barcode_id),
            ]
        )

    def validate(self) -> bool:
        if not super().validate():
            return False

        duplicate_barcode = self.df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)
        
        for idx, row in self.df.iterrows():
            if pd.notna(row["barcode_id"]) and duplicate_barcode.at[idx]:
                self.spreadsheet.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."))

        if len(self.spreadsheet._errors) > 0:
            return False

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.flex_table["mux_barcode"] = utils.map_columns(self.flex_table, self.df, ["sample_id", "library_id"], "barcode_id")
        self.tables["sample_table"] = self.sample_table

        if FlexABCForm.is_applicable(self):
            self.tables["gex_table"] = self.flex_table
            self.step()
            form = FlexABCForm(lab_prep=self.lab_prep, uuid=self.uuid)
            return form.make_response()

        CommonFlexMuxForm.update_barcodes(self.flex_table)
        self.complete()
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id, tab="mux-tab")))