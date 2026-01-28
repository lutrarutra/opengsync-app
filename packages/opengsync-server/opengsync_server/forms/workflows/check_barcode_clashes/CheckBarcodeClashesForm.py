from typing import Literal

import pandas as pd

from flask import Response

from .... import tools
from ...HTMXFlaskForm import HTMXFlaskForm


class CheckBarcodeClashesForm(HTMXFlaskForm):
    _template_path = "workflows/check_barcode_clashes/clashes-1.html"
    _form_label = "check_barcode_clashes_form"

    def __init__(self, libraries_df: pd.DataFrame, groupby: Literal["lane", "pool"] | None = None, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.libraries_df = libraries_df
        self.groupby = groupby
        self._context["groupby"] = groupby
    
    def process_request(self) -> Response:
        if self.groupby is None:
            self.libraries_df = tools.check_indices(self.libraries_df)
        elif self.groupby == "pool":
            self.libraries_df = tools.check_indices(self.libraries_df, groupby="pool_id").sort_values(["pool_id", "library_id"])
        elif self.groupby == "lane":
            self.libraries_df = tools.check_indices(self.libraries_df, groupby="lane_id").sort_values(["lane", "library_id"])

        return self.make_response(
            df=self.libraries_df, warn_user=self.libraries_df["error"].notna().any() or self.libraries_df["warning"].notna().any()
        )