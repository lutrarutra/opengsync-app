import pandas as pd

from flask import Response, url_for, flash
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms import FloatField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models

from .... import db
from ...HTMXFlaskForm import HTMXFlaskForm


class PoolingRatioSubForm(FlaskForm):
    qubit_after_dilution = FloatField("Qubit Concentration After Dilution", validators=[OptionalValidator()])


class DilutePoolsForm(HTMXFlaskForm):
    _template_path = "workflows/dilute_pools/dilute-1.html"
    _form_label = "dilute_pools_form"

    input_fields = FieldList(FormField(PoolingRatioSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        
    def prepare(self, experiment: models.Experiment) -> dict:
        df = db.get_experiment_pools_df(experiment.id)

        df["qubit_concentration"] = df.apply(lambda row: row["original_qubit_concentration"] if pd.isna(row["diluted_qubit_concentration"]) else row["diluted_qubit_concentration"], axis="columns")

        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
        df["molarity_color"] = "cemm-green"
        df.loc[(df["molarity"] < models.Pool.warning_min_molarity) | (models.Pool.warning_max_molarity < df["molarity"]), "molarity_color"] = "cemm-yellow"
        df.loc[(df["molarity"] < models.Pool.error_min_molarity) | (models.Pool.error_max_molarity < df["molarity"]), "molarity_color"] = "cemm-red"

        for i in range(df.shape[0]):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

        return {"df": df, "enumerate": enumerate}
    
    def process_request(self, **context) -> Response:
        experiment: models.Experiment = context["experiment"]
        df = db.get_experiment_pools_df(experiment.id)

        if not self.validate():
            context["df"] = df
            context["enumerate"] = enumerate
            return self.make_response(**context)
        
        for i, (_, row) in enumerate(df.iterrows()):
            entry = self.input_fields[i]
            if entry.qubit_after_dilution.data is None:
                continue
            
            if (pool := db.get_pool(row["id"])) is None:
                raise ValueError(f"Pool with id {row['id']} not found")
            
            pool.diluted_qubit_concentration = entry.qubit_after_dilution.data
            db.update_pool(pool)

        flash("Dilution successful!", "success")
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))