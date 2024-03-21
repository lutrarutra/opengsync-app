from typing import Optional

import pandas as pd

from flask import Response
from wtforms import StringField

from limbless_db import models

from .... import db
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .PoolingRatioForm import PoolingRatioForm


class BarcodeCheckForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/lane_pools/lp-1.html"
    _form_label = "barcode_check_form"

    pool_ids = StringField()

    def __init__(self, formdata: dict = {}):
        uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, "lane_pools", None)

    def prepare(self, experiment_id) -> dict:

        df = db.get_experiment_libraries_df(experiment_id, include_reads_requested=True)
            
        df["error"] = None
        df["warning"] = None

        indices = ["index_1"]
        if "index_2" in df.columns and not df["index_2"].isna().all():
            indices.append("index_2")
        if "index_3" in df.columns and not df["index_3"].isna().all():
            indices.append("index_3")
        if "index_4" in df.columns and not df["index_4"].isna().all():
            indices.append("index_4")

        if "index_2" in df.columns:
            same_barcode_in_different_indices = df["index_1"] == df["index_2"]
            if "index_3" in df.columns:
                same_barcode_in_different_indices |= df["index_2"] == df["index_3"]
            if "index_4" in df.columns:
                same_barcode_in_different_indices |= df["index_2"] == df["index_4"]
        if "index_3" in df.columns:
            same_barcode_in_different_indices |= df["index_1"] == df["index_3"]
            if "index_4" in df.columns:
                same_barcode_in_different_indices |= df["index_3"] == df["index_4"]
        if "index_4" in df.columns:
            same_barcode_in_different_indices |= df["index_1"] == df["index_4"]

        df.loc[same_barcode_in_different_indices, "warning"] = "Same barcode in different indices"

        for lane, _df in df.groupby("lane"):
            for index in indices:
                reused_barcodes = _df[index].duplicated(keep=False)
                if reused_barcodes.any():
                    df.loc[_df[reused_barcodes].index, "warning"] = f"Reused barcode in {index.replace('_', ' ').title()}"

            reused_barcode_combination = _df[indices].duplicated(keep=False)
            df.loc[_df[reused_barcode_combination].index, "error"] = "Reused barcode combination"

        df = df.sort_values(["lane", "pool_name", "library_id"])

        data: dict[str, pd.DataFrame | dict] = dict(
            library_table=df
        )
        self.update_data(data)

        return {
            "df": df,
            "show_index_1": "index_1" in indices,
            "show_index_2": "index_2" in indices,
            "show_index_3": "index_3" in indices,
            "show_index_4": "index_4" in indices,
            "show_adapter": "adapter" in df.columns and not df["adapter"].isna().all(),
            "warn_user": df["error"].notna().any() or df["warning"].notna().any(),
        }

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response()
        
        data = self.get_data()

        df: pd.DataFrame = data["library_table"]  # type: ignore
        df = df[["pool_id", "pool_name", "lane", "pool_reads_requested"]].drop_duplicates().sort_values(["lane", "pool_id"])
        data["pool_table"] = df
        self.update_data(data)

        lane_pooling_form = PoolingRatioForm(self.uuid)
        context = lane_pooling_form.prepare(data) | context
        return lane_pooling_form.make_response(**context)