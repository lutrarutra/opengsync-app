import pandas as pd

from flask import Response, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, FieldList, FormField
from wtforms.validators import DataRequired

from limbless_db import models
from limbless_db.categories import ExperimentStatus

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm


class QCLanesSubForm(FlaskForm):
    lane_id = IntegerField("Lane ID", validators=[DataRequired()])
    # phi_x = FloatField("Phi X %", validators=[DataRequired()])
    avg_library_size = IntegerField("Average Library Size", validators=[DataRequired()])
    qubit_concentration = FloatField("Qubit Concentration", validators=[DataRequired()])
    # desired_molarity = FloatField("Desired Molarity", validators=[DataRequired()])
    # total_volume_ul = FloatField("Total Volume (µL)", validators=[DataRequired()])


class QCLanesForm(HTMXFlaskForm):
    _template_path = "workflows/lane_qc/lqc-1.html"
    _form_label = "lane_qc_form"

    input_fields = FieldList(FormField(QCLanesSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity

    def prepare(self, experiment: models.Experiment) -> dict:
        df = db.get_experiment_lanes_df(experiment.id)

        for i, (_, row) in enumerate(df.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            self.input_fields[i].lane_id.data = int(row["id"])
            # self.input_fields[i].total_volume_ul.data = experiment.workflow.volume_target_ul

            # if pd.notna(df.at[idx, "phi_x"]):
            #     self.input_fields[i].phi_x.data = df.at[idx, "phi_x"]

            if pd.notna(row["qubit_concentration"]):
                self.input_fields[i].qubit_concentration.data = row["qubit_concentration"]

            # if pd.notna(df.at[idx, "total_volume_ul"]):
            #     self.input_fields[i].total_volume_ul.data = df.at[idx, "total_volume_ul"]

            if pd.notna(row["avg_library_size"]):
                self.input_fields[i].avg_library_size.data = int(row["avg_library_size"])

        return {"df": df, "enumerate": enumerate}
    
    def process_request(self, **context) -> Response:
        experiment: models.Experiment = context["experiment"]

        if not self.validate():
            df = db.get_experiment_lanes_df(experiment.id)
            context["df"] = df
            context["enumerate"] = enumerate
            return self.make_response(**context)
        
        for sub_form in self.input_fields:
            if (lane := db.get_lane(sub_form.lane_id.data)) is None:
                logger.error(f"Lane with id {sub_form.lane_id.data} not found")
                raise ValueError(f"Lane with id {sub_form.lane_id.data} not found")
                
            lane.qubit_concentration = sub_form.qubit_concentration.data
            lane.avg_library_size = sub_form.avg_library_size.data

            lane = db.update_lane(lane)

        experiment.status_id = ExperimentStatus.LOADED.id
        experiment = db.update_experiment(experiment)

        flash("Flow cell loaded successfully", "success")
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))