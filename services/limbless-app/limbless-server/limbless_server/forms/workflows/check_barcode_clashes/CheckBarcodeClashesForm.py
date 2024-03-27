import scipy
import numpy as np

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

        df["combined_index"] = ""
        for index in indices:
            _max = df[index].str.len().max()
            df["combined_index"] += df[index].apply(lambda x: x + " " * (_max - len(x)) if x is not None else "")

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

        df["min_hamming_dist"] = None
        df["min_idx"] = None

        def hamming(x, y):
            return scipy.spatial.distance.hamming(list(x[0]), list(y[0]))

        for lane, _df in df.groupby("lane"):
            a = np.array(_df["combined_index"]).reshape(-1, 1)
            dists = scipy.spatial.distance.pdist(a, lambda x, y: hamming(x, y))
            p_dist = scipy.spatial.distance.squareform(dists)
            np.fill_diagonal(p_dist, np.nan)
            min_idx = np.nanargmin(p_dist, axis=0)
            df.loc[_df.index, "min_idx"] = min_idx
            df.loc[_df.index, "min_hamming_dist"] = p_dist[np.arange(p_dist.shape[0]), min_idx]

        df["min_hamming_bases"] = df["min_hamming_dist"] * df["combined_index"].apply(lambda x: len(x))
        df["min_hamming_bases"] = df["min_hamming_bases"].astype(int)

        df.loc[df["min_hamming_bases"] < 1, "error"] = "Hamming distance of 0 between barcode combination in two or more libraries on same lane."
        df.loc[df["min_hamming_bases"] < 3, "warning"] = "Small hamming distance between barcode combination in two or more libraries on same lane."

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