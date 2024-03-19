from typing import Optional

import pandas as pd

from flask import Response
from wtforms import StringField

from limbless_db import models

from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .PoolingRatioForm import PoolingRatioForm


class BarcodeCheckForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/lane_pools/lp-2.html"
    _form_label = "barcode_check_form"

    pool_ids = StringField()

    def __init__(self, experiment: models.Experiment, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=None)
        self.experiment = experiment
        self._context["experiment"] = experiment

    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()

        library_table: pd.DataFrame = data["library_table"]  # type: ignore

        library_table["error"] = None
        library_table["warning"] = None

        indices = ["index_1"]
        if not library_table["index_2"].isna().all():
            indices.append("index_2")
        if not library_table["index_3"].isna().all():
            indices.append("index_3")
        if not library_table["index_4"].isna().all():
            indices.append("index_4")

        reused_barcode_combination = library_table[indices].duplicated(keep=False)

        for index in indices:
            reused_barcodes = library_table[index].duplicated(keep=False)
            if reused_barcodes.any():
                library_table.loc[reused_barcodes, "warning"] = f"Reused barcode in {index.replace('_', ' ').title()}"

        library_table.loc[reused_barcode_combination, "error"] = "Reused barcode combination"

        self.update_data(data)

        return {
            "library_table": library_table,
            "show_index_1": not library_table["index_1"].isna().all(),
            "show_index_2": not library_table["index_2"].isna().all(),
            "show_index_3": not library_table["index_3"].isna().all(),
            "show_index_4": not library_table["index_4"].isna().all(),
            "show_adapter": not library_table["adapter"].isna().all(),
            "warn_user": library_table["error"].notna().any() or library_table["warning"].notna().any(),
        }

    def validate(self) -> bool:
        
        return True

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response()
        
        data = self.get_data()
        
        lane_pooling_form = PoolingRatioForm(self.experiment, self.formdata)
        context = lane_pooling_form.prepare(data) | context
        return lane_pooling_form.make_response(**context)