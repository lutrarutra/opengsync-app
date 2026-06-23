from __future__ import annotations

from typing import Literal

import pandas as pd
from fastapi import Request

from ..HTMXForm import HTMXForm
from ...core import barcode_utils


class CheckBarcodeClashesForm(HTMXForm):
    """Form that renders a barcode clash check result table.

    Unlike typical HTMXForms this does NOT have input fields for user
    submission — it is a display-only form that processes a pre-built
    library barcode DataFrame and renders the clash results.
    """

    template_path = "workflows/check_barcode_clashes/clashes-1.html"

    def __init__(
        self,
        request: Request,
        libraries_df: pd.DataFrame,
        groupby: Literal["lane", "pool"] | None = None,
    ):
        super().__init__(request)
        self.libraries_df = libraries_df
        self.groupby = groupby
        self._context["groupby"] = groupby

    async def prepare(self) -> None:
        """Run the barcode clash check and store result in context."""
        if self.groupby is None:
            self.libraries_df = barcode_utils.check_indices(self.libraries_df)
        elif self.groupby == "pool":
            self.libraries_df = (
                barcode_utils.check_indices(self.libraries_df, groupby="pool_id")
                .sort_values(["pool_id", "library_id"])
            )
        elif self.groupby == "lane":
            self.libraries_df = (
                barcode_utils.check_indices(self.libraries_df, groupby="lane_id")
                .sort_values(["lane", "library_id"])
            )

        self._context["df"] = self.libraries_df
        self._context["warn_user"] = (
            self.libraries_df["error"].notna().any()
            or self.libraries_df["warning"].notna().any()
        )