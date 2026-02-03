import pandas as pd

from flask import Response, flash, url_for
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms import FloatField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from opengsync_db import models
from opengsync_db.categories import ExperimentStatus

from .... import db, logger 
from ...HTMXFlaskForm import HTMXFlaskForm


class SubForm(FlaskForm):
    lane_id = FloatField("Lane ID", validators=[DataRequired()])
    phi_x = FloatField("Phi X %", validators=[DataRequired()])

    measured_qubit = FloatField("Qubit Concentration After Dilution", validators=[OptionalValidator()])
    target_molarity = FloatField("Target Molarity", validators=[OptionalValidator()])
    total_volume_ul = FloatField("Total Volume", validators=[OptionalValidator()])


class LoadFlowCellForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/load_flow_cell-1.1.html"
    _form_label = "load_flow_cell_form"

    input_fields = FieldList(FormField(SubForm), min_entries=1)

    def __init__(self, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity
        self._context["enumerate"] = enumerate
        self._context["experiment"] = experiment

        self.lane_table = db.pd.get_experiment_lanes(self.experiment.id)
        self.lane_table["library_volume"] = None
        self.lane_table["eb_volume"] = None

        for idx, row in self.lane_table.iterrows():
            if pd.notna(row["total_volume_ul"]):
                total_volume_ul = row["total_volume_ul"]
            else:
                total_volume_ul = self.experiment.workflow.volume_target_ul

            if pd.notna(row["target_molarity"]):
                library_volume = total_volume_ul * row["target_molarity"] / row["lane_molarity"]
                self.lane_table.at[idx, "library_volume"] = library_volume  # type: ignore
                self.lane_table.at[idx, "eb_volume"] = total_volume_ul - library_volume  # type: ignore

    def prepare(self):
        for i, (idx, row) in enumerate(self.lane_table.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.lane_id.data = int(row["id"])

            if pd.notna(row["total_volume_ul"]):
                entry.total_volume_ul.data = row["total_volume_ul"]
            else:
                entry.total_volume_ul.data = self.experiment.workflow.volume_target_ul

            if pd.notna(row["sequencing_qubit_concentration"]):
                entry.measured_qubit.data = row["sequencing_qubit_concentration"]

            if pd.notna(row["target_molarity"]):
                entry.target_molarity.data = row["target_molarity"]
                library_volume = entry.total_volume_ul.data * row["target_molarity"] / row["lane_molarity"]
                self.lane_table.at[idx, "library_volume"] = library_volume  # type: ignore
                self.lane_table.at[idx, "eb_volume"] = entry.total_volume_ul.data - library_volume  # type: ignore

            if pd.notna(row["phi_x"]):
                entry.phi_x.data = row["phi_x"]

        self._context["df"] = self.lane_table
    
    def process_request(self) -> Response:
        if not self.validate():
            self.lane_table["qubit_concentration"] = self.lane_table.apply(lambda row: row["original_qubit_concentration"] if pd.isna(row["sequencing_qubit_concentration"]) else row["sequencing_qubit_concentration"], axis="columns")
            self.lane_table["molarity"] = self.lane_table["qubit_concentration"] / (self.lane_table["avg_fragment_size"] * 660) * 1_000_000
            self._context["df"] = self.lane_table
            logger.debug(self.lane_table)
            return self.make_response()
        
        all_lanes_loaded = True
        for i, (_, row) in enumerate(self.lane_table.iterrows()):
            entry = self.input_fields[i]
            
            if (lane := db.lanes.get(entry.lane_id.data)) is None:
                raise ValueError(f"Lane with id {row['id']} not found")
            
            lane.target_molarity = entry.target_molarity.data
            lane.total_volume_ul = entry.total_volume_ul.data
            lane.sequencing_qubit_concentration = entry.measured_qubit.data
            lane.phi_x = entry.phi_x.data
            if (lane.total_volume_ul is not None) and (lane.target_molarity is not None) and (lane.original_molarity is not None):
                lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane.original_molarity  # type: ignore
            db.lanes.update(lane)
            all_lanes_loaded = all_lanes_loaded and lane.is_loaded()
            logger.debug(f"Lane {lane.id} loaded: {lane.is_loaded()}")

        if all_lanes_loaded:
            self.experiment.status = ExperimentStatus.LOADED
            db.experiments.update(self.experiment)

        flash("Saved!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))
