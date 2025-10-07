from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import MUXType, LibraryType

from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, IntegerColumn
from ..common.CommonFlexMuxForm import CommonFlexMuxForm


class FlexReMuxForm(CommonFlexMuxForm):
    _template_path = "workflows/library_remux/flex_annotation.html"
    _workflow_name = "library_remux"
    library: models.Library

    allowed_barcodes = [f"BC{i:03}" for i in range(1, 17)]
    abc_allowed_barcodes = [f"AB{i:03}" for i in range(1, 17)]

    def __init__(self, library: models.Library, formdata: dict | None = None, uuid: Optional[str] = None):
        match library.type:
            case LibraryType.TENX_SC_GEX_FLEX:
                allowed_barcodes = FlexReMuxForm.allowed_barcodes
            case LibraryType.TENX_SC_ABC_FLEX:
                allowed_barcodes = FlexReMuxForm.abc_allowed_barcodes
            case _:
                raise ValueError(f"Library type {library.type} is not supported for FlexReMuxForm")

        CommonFlexMuxForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexReMuxForm._workflow_name,
            seq_request=None, library=library, lab_prep=None, columns=[
                IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
                IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
                TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
                TextColumn(
                    "barcode_id", "Bardcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH,
                    validation_fnc=lambda b: b in allowed_barcodes or pd.isna(b),
                ),
            ]
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.flex_table["mux_barcode"] = utils.map_columns(self.flex_table, self.df, ["sample_id", "library_id"], "barcode_id")
        CommonFlexMuxForm.update_barcodes(sample_table=self.flex_table)

        self.complete()
        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("libraries_page.library", library_id=self.library.id)))