import numpy as np

from flask import Response, url_for
from flask_htmx import make_response

from .... import db, tools
from ...HTMXFlaskForm import HTMXFlaskForm


class CheckBarcodeClashesForm(HTMXFlaskForm):
    _template_path = "workflows/check_barcode_clashes/clashes-1.html"
    _form_label = "check_barcode_clashes_form"

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)

    def prepare(self, experiment_id) -> dict:
        df = db.get_experiment_libraries_df(experiment_id, collapse_lanes=False)
        df = tools.check_indices(df, "lane")
        df = df.sort_values(["lane", "pool_name", "library_id"])

        return {
            "df": df,
            "show_index_1": "index_1" in df.columns and not df["index_1"].isna().all(),
            "show_index_2": "index_2" in df.columns and not df["index_2"].isna().all(),
            "show_index_3": "index_3" in df.columns and not df["index_3"].isna().all(),
            "show_index_4": "index_4" in df.columns and not df["index_4"].isna().all(),
            "show_adapter": "adapter" in df.columns and not df["adapter"].isna().all(),
            "warn_user": df["error"].notna().any() or df["warning"].notna().any(),
        }
    
    def process_request(self, **context) -> Response:
        experiment = context["experiment"]
        if not self.validate():
            return self.make_response()

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))