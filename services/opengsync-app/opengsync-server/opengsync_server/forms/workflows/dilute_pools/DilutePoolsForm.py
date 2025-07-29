from flask import Response, url_for, flash
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms import FloatField, FieldList, FormField, IntegerField
from wtforms.validators import DataRequired, Optional as OptionalValidator

from opengsync_db import models

from .... import db
from ...HTMXFlaskForm import HTMXFlaskForm


class PoolingRatioSubForm(FlaskForm):
    qubit_after_dilution = FloatField(validators=[OptionalValidator()])
    pool_id = IntegerField(validators=[DataRequired()])


class DilutePoolsForm(HTMXFlaskForm):
    _template_path = "workflows/dilute_pools/dilute-1.html"
    _form_label = "dilute_pools_form"

    input_fields = FieldList(FormField(PoolingRatioSubForm), min_entries=1)
    target_total_volume = FloatField(validators=[DataRequired()], default=50)
    target_molarity = FloatField("Target Molarity", validators=[DataRequired()], default=3.0)

    def __init__(self, experiment: models.Experiment, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self._context["enumerate"] = enumerate
        self.experiment = experiment
        self.df = db.get_experiment_pools_df(experiment.id)
        
    def prepare(self):
        self.df["molarity"] = self.df["qubit_concentration"] / (self.df["avg_fragment_size"] * 660) * 1_000_000
        self.df["molarity_color"] = "cemm-green"
        self.df.loc[(self.df["molarity"] < models.Pool.warning_min_molarity) | (models.Pool.warning_max_molarity < self.df["molarity"]), "molarity_color"] = "cemm-yellow"
        self.df.loc[(self.df["molarity"] < models.Pool.error_min_molarity) | (models.Pool.error_max_molarity < self.df["molarity"]), "molarity_color"] = "cemm-red"

        for i in range(self.df.shape[0]):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

        self._context["df"] = self.df
        self._context["enumerate"] = enumerate
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response(df=self.df)
        
        for i, (_, row) in enumerate(self.df.iterrows()):
            entry = self.input_fields[i]
            if entry.qubit_after_dilution.data is None:
                continue
            
            pool_id = int(entry.pool_id.data)
            
            if db.get_pool(pool_id) is None:
                raise ValueError(f"Pool with id {row['id']} not found")
            
            db.dilute_pool(pool_id, entry.qubit_after_dilution.data, user.id)

        flash("Dilution successful!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))