from typing import Optional

import pandas as pd

from flask import Response, flash, url_for
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms import IntegerField, FloatField, FieldList, FormField
from wtforms.validators import DataRequired, NumberRange

from limbless_db import models, DBHandler
from limbless_db.categories import ExperimentStatus, PoolStatus

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm


class PoolQCSubForm(FlaskForm):
    avg_library_size = IntegerField(validators=[DataRequired(), NumberRange(min=0)])
    qubit_concentration = FloatField(validators=[DataRequired(), NumberRange(min=0)])


class PoolQCForm(HTMXFlaskForm,):
    _template_path = "workflows/pool_qc/pqc-1.html"
    _form_label = "pool_qc_form"

    input_fields = FieldList(FormField(PoolQCSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        
    def prepare(self, experiment: models.Experiment) -> dict:
        df = db.get_experiment_pools_df(experiment.id).sort_values("id")

        for i, (idx, row) in enumerate(df.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            if pd.notna(df.at[idx, "avg_library_size"]):
                self.input_fields[i].avg_library_size.data = df.at[idx, "avg_library_size"]
            if pd.notna(df.at[idx, "qubit_concentration"]):
                self.input_fields[i].qubit_concentration.data = df.at[idx, "qubit_concentration"]

        return {"df": df, "enumerate": enumerate}
    
    def process_request(self, **context) -> Response:
        experiment = context["experiment"]
        session: DBHandler = context["session"]
        df = db.get_experiment_pools_df(experiment.id).sort_values("name")
        if not self.validate():
            context["df"] = df
            context["enumerate"] = enumerate
            return self.make_response(**context)

        for i, (_, row) in enumerate(df.iterrows()):
            entry = self.input_fields[i]
            if (pool := db.get_pool(row["id"])) is None:
                logger.error(f"Pool with id {row['id']} not found")
                raise ValueError(f"Pool with id {row['id']} not found")
                
            pool.avg_library_size = entry.avg_library_size.data
            pool.qubit_concentration = entry.qubit_concentration.data

            session.update_pool(pool)

        flash("Pool QC data saved", "success")
        experiment.status_id = ExperimentStatus.POOLS_QCED.id
        experiment = session.update_experiment(experiment)
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))