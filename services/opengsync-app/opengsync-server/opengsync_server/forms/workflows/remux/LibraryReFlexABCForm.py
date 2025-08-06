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


class LibraryReFlexABCForm(CommonFlexABCForm):
    _template_path = "workflows/library_remux/flex_annotation.html"
    _workflow_name = "library_remux"
    abc_table: pd.DataFrame
    gex_table: pd.DataFrame
    sample_table: pd.DataFrame
    library: models.Library
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
        TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=padded_barcode_id),
    ]

    allowed_barcodes = [f"AB{i:03}" for i in range(1, 17)]
    mux_type = MUXType.TENX_FLEX_PROBE

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        sample_table = current_step.tables["sample_table"]
        return LibraryType.TENX_SC_ABC_FLEX in sample_table["library_type"].values

    def __init__(self, library: models.Library, formdata: dict | None = None, uuid: Optional[str] = None):
        CommonFlexABCForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=LibraryReFlexABCForm._workflow_name,
            lab_prep=None, seq_request=None, library=library, columns=LibraryReFlexABCForm.columns
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.abc_table["mux_barcode"] = utils.map_columns(self.abc_table, self.df, ["sample_name", "library_id"], "barcode_id")

        CommonFlexMuxForm.update_barcodes(self.abc_table)
        
        self.complete()
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("libraries_page.library", library_id=self.library.id, tab="library-multiplexing-tab")))