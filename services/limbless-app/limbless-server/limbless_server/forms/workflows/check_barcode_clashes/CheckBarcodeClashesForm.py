import pandas as pd

from flask import Response, url_for
from flask_htmx import make_response

from .... import db
from ...HTMXFlaskForm import HTMXFlaskForm


class CheckBarcodeClashesForm(HTMXFlaskForm):
    _template_path = "workflows/check_barcode_clashes/clashes-1.html"
    _form_label = "check_barcode_clashes_form"

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)

    def prepare(self, experiment_id) -> dict:
        df = db.get_experiment_libraries_df(experiment_id)
            
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

        return {
            "df": df,
            "show_index_1": "index_1" in indices,
            "show_index_2": "index_2" in indices,
            "show_index_3": "index_3" in indices,
            "show_index_4": "index_4" in indices,
            "show_adapter": "adapter" in df.columns and not df["adapter"].isna().all(),
            "warn_user": df["error"].notna().any() or df["warning"].notna().any(),
        }
    
    def process_request(self, **context) -> Response:
        experiment = context["experiment"]
        if not self.validate():
            return self.make_response()

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))