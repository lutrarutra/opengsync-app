import pandas as pd

from flask import Response, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, FieldList, FormField
from wtforms.validators import DataRequired

from opengsync_db import models

from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm


class UnifiedQCLanesForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/lane_qc-1.2.html"
    _form_label = "lane_qc_form"

    phi_x = FloatField("Phi X %", validators=[DataRequired()])
    avg_fragment_size = IntegerField("Average Library Size", validators=[DataRequired()])
    qubit_concentration = FloatField("Qubit Concentration", validators=[DataRequired()])

    def __init__(self, experiment: models.Experiment, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity
        self._context["experiment"] = experiment
        self._context["enumerate"] = enumerate

    def prepare(self):
        df = db.get_experiment_lanes_df(self.experiment.id)
        df["qubit_concentration"] = df.apply(lambda row: row["original_qubit_concentration"] if pd.isna(row["sequencing_qubit_concentration"]) else row["sequencing_qubit_concentration"], axis="columns")
        df = df.drop(columns=["lane"]).reset_index(drop=True)

        row = df.iloc[0]
        self.phi_x.data = row["phi_x"] if pd.notna(row["phi_x"]) else None
        self.avg_fragment_size.data = int(row["avg_fragment_size"]) if pd.notna(row["avg_fragment_size"]) else None
        self.qubit_concentration.data = row["qubit_concentration"] if pd.notna(row["qubit_concentration"]) else None
        self._context["df"] = df
    
    def process_request(self) -> Response:
        if not self.validate():
            df = db.get_experiment_lanes_df(self.experiment.id)
            self._context["df"] = df
            return self.make_response()

        for lane in self.experiment.lanes:
            lane.phi_x = self.phi_x.data
            lane.avg_fragment_size = self.avg_fragment_size.data
            lane.original_qubit_concentration = self.qubit_concentration.data

            db.update_lane(lane)

        flash("Flow cell loaded successfully", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))


class QCLanesSubForm(FlaskForm):
    lane_id = IntegerField("Lane ID", validators=[DataRequired()])
    phi_x = FloatField("Phi X %", validators=[DataRequired()])
    avg_fragment_size = IntegerField("Average Library Size", validators=[DataRequired()])
    qubit_concentration = FloatField("Qubit Concentration", validators=[DataRequired()])


class QCLanesForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/lane_qc-1.1.html"
    _form_label = "lane_qc_form"

    input_fields = FieldList(FormField(QCLanesSubForm), min_entries=1)

    def __init__(self, experiment: models.Experiment, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity
        self._context["enumerate"] = enumerate

    def prepare(self):
        df = db.get_experiment_lanes_df(self.experiment.id)
        df["qubit_concentration"] = df.apply(lambda row: row["original_qubit_concentration"] if pd.isna(row["sequencing_qubit_concentration"]) else row["sequencing_qubit_concentration"], axis="columns")

        for i, (_, row) in enumerate(df.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            self.input_fields[i].lane_id.data = int(row["id"])

            if pd.notna(row["phi_x"]):
                self.input_fields[i].phi_x.data = row["phi_x"]

            if pd.notna(row["qubit_concentration"]):
                self.input_fields[i].qubit_concentration.data = row["qubit_concentration"]

            if pd.notna(row["avg_fragment_size"]):
                self.input_fields[i].avg_fragment_size.data = int(row["avg_fragment_size"])

        self._context["df"] = df
    
    def process_request(self) -> Response:
        if not self.validate():
            df = db.get_experiment_lanes_df(self.experiment.id)
            self._context["df"] = df
            return self.make_response()
        
        for sub_form in self.input_fields:
            if (lane := db.get_lane(sub_form.lane_id.data)) is None:
                logger.error(f"Lane with id {sub_form.lane_id.data} not found")
                raise ValueError(f"Lane with id {sub_form.lane_id.data} not found")
                
            lane.original_qubit_concentration = sub_form.qubit_concentration.data
            lane.avg_fragment_size = sub_form.avg_fragment_size.data
            lane.phi_x = sub_form.phi_x.data

            lane = db.update_lane(lane)

        flash("Flow cell loaded successfully", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))