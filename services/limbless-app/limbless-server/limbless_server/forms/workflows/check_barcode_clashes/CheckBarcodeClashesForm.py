from flask import Response, url_for
from flask_htmx import make_response

from limbless_db import models

from .... import db, tools
from ...HTMXFlaskForm import HTMXFlaskForm


class CheckBarcodeClashesForm(HTMXFlaskForm):
    _template_path = "workflows/check_barcode_clashes/clashes-1.html"
    _form_label = "check_barcode_clashes_form"

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)

    def prepare(self, experiment_id) -> dict:
        df = db.get_experiment_barcodes_df(experiment_id)
        df = tools.check_indices(df, "lane")
        df = df.sort_values(["lane", "pool_name", "library_id"])

        return {
            "df": df,
            "warn_user": df["error"].notna().any() or df["warning"].notna().any(),
        }
    
    def process_request(self, experiment: models.Experiment) -> Response:
        if not self.validate():
            return self.make_response()

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))