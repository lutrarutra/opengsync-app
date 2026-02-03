import pandas as pd

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import FloatField, IntegerField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from opengsync_db import models
from opengsync_db.categories import ExperimentStatus

from .... import db, logger 
from ...HTMXFlaskForm import HTMXFlaskForm


class UnifiedLoadFlowCellForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/load_flow_cell-1.2.html"

    phi_x = FloatField("Phi X %", validators=[DataRequired()])
    measured_qubit = FloatField(validators=[OptionalValidator()])
    target_molarity = FloatField(validators=[OptionalValidator()])
    total_volume_ul = FloatField(validators=[OptionalValidator()])

    avg_fragment_size = IntegerField("Avg. Fragment Size")
    qubit_concentration = FloatField("Qubit Concentration")
    lane_molarity = FloatField("Lane Molarity")
    sequencing_molarity = FloatField("Sequencing Molarity")
    library_volume = FloatField("Library Volume")
    eb_volume = FloatField("EB Volume")

    def __init__(self, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity
        self._context["enumerate"] = enumerate
        self._context["experiment"] = experiment

    def prepare(self):
        df = db.pd.get_experiment_lanes(self.experiment.id)
        row = df.iloc[0]

        if pd.notna(row["total_volume_ul"]):
            self.total_volume_ul.data = row["total_volume_ul"]
        else:
            self.total_volume_ul.data = self.experiment.workflow.volume_target_ul

        if pd.notna(row["sequencing_qubit_concentration"]):
            self.measured_qubit.data = row["sequencing_qubit_concentration"]

        if pd.notna(row["target_molarity"]):
            self.target_molarity.data = row["target_molarity"]
            library_volume = self.total_volume_ul.data * row["target_molarity"] / row["lane_molarity"]
            eb_volume = self.total_volume_ul.data - library_volume
        else:
            library_volume = None
            eb_volume = None

        if pd.notna(row["sequencing_qubit_concentration"]) and pd.notna(row["avg_fragment_size"]):
            sequencing_molarity = row["sequencing_qubit_concentration"] / (row["avg_fragment_size"] * 660) * 1_000_000
        else:
            sequencing_molarity = None

        if pd.notna(row["phi_x"]):
            self.phi_x.data = row["phi_x"]

        self.avg_fragment_size.data = row["avg_fragment_size"]
        self.qubit_concentration.data = row["original_qubit_concentration"]
        self.lane_molarity.data = row["lane_molarity"]
        self.sequencing_molarity.data = sequencing_molarity
        self.library_volume.data = library_volume
        self.eb_volume.data = eb_volume
    
    def process_request(self) -> Response:
        if not self.validate():
            self._context["df"] = db.pd.get_experiment_lanes(self.experiment.id)
            return self.make_response()

        loaded = True
        for lane in self.experiment.lanes:
            lane.total_volume_ul = self.total_volume_ul.data
            lane.sequencing_qubit_concentration = self.measured_qubit.data
            lane.target_molarity = self.target_molarity.data
            lane.phi_x = self.phi_x.data
            if ((lane_molarity := lane.original_molarity) is not None) and (lane.target_molarity is not None) and (lane.total_volume_ul is not None):
                lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane_molarity  # type: ignore
            else:
                loaded = False

            db.lanes.update(lane)

        if loaded:
            self.experiment.status = ExperimentStatus.LOADED
            db.experiments.update(self.experiment)

        flash("Saved!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))


