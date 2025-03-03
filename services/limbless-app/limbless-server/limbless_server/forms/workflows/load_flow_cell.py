import pandas as pd

from flask import Response, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import FloatField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import ExperimentStatus

from ... import db, logger   # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class UnifiedLoadFlowCellForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/load_flow_cell-1.2.html"

    measured_qubit = FloatField(validators=[OptionalValidator()])
    target_molarity = FloatField(validators=[OptionalValidator()])
    total_volume_ul = FloatField(validators=[OptionalValidator()])

    def __init__(self, experiment: models.Experiment, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["warning_min"] = models.Lane.warning_min_molarity
        self._context["warning_max"] = models.Lane.warning_max_molarity
        self._context["error_min"] = models.Lane.error_min_molarity
        self._context["error_max"] = models.Lane.error_max_molarity
        self._context["enumerate"] = enumerate
        self._context["experiment"] = experiment

    def __get_params(self, df: pd.DataFrame):
        row = df.iloc[0]
        lane_molarity = row["original_qubit_concentration"] / (row["avg_fragment_size"] * 660) * 1_000_000

        if pd.notna(row["total_volume_ul"]):
            self.total_volume_ul.data = row["total_volume_ul"]
        else:
            self.total_volume_ul.data = self.experiment.workflow.volume_target_ul

        if pd.notna(row["sequencing_qubit_concentration"]):
            self.measured_qubit.data = row["sequencing_qubit_concentration"]

        if pd.notna(row["target_molarity"]):
            self.target_molarity.data = row["target_molarity"]
            library_volume = self.total_volume_ul.data * row["target_molarity"] / lane_molarity
            eb_volume = self.total_volume_ul.data - library_volume
        else:
            library_volume = None
            eb_volume = None

        if pd.notna(row["sequencing_qubit_concentration"]) and pd.notna(row["avg_fragment_size"]):
            sequencing_molarity = row["sequencing_qubit_concentration"] / (row["avg_fragment_size"] * 660) * 1_000_000
        else:
            sequencing_molarity = None

        self._context["avg_fragment_size"] = row["avg_fragment_size"]
        self._context["lane_molarity"] = lane_molarity
        self._context["library_volume"] = library_volume
        self._context["eb_volume"] = eb_volume
        self._context["sequencing_molarity"] = sequencing_molarity

    def prepare(self):
        df = db.get_experiment_lanes_df(self.experiment.id)
        self.__get_params(df)
    
    def process_request(self) -> Response:
        if not self.validate():
            self._context["df"] = db.get_experiment_lanes_df(self.experiment.id)
            return self.make_response()

        loaded = True
        for lane in self.experiment.lanes:
            lane.total_volume_ul = self.total_volume_ul.data
            lane.sequencing_qubit_concentration = self.measured_qubit.data
            lane.target_molarity = self.target_molarity.data
            if ((lane_molarity := lane.original_molarity) is not None) and (lane.target_molarity is not None) and (lane.total_volume_ul is not None):
                lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane_molarity  # type: ignore
            else:
                loaded = False

            lane = db.update_lane(lane)

        if loaded:
            self.experiment.status = ExperimentStatus.LOADED
            experiment = db.update_experiment(self.experiment)

        flash("Saved!", "success")
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))


class SubForm(FlaskForm):
    measured_qubit = FloatField("Qubit Concentration After Dilution", validators=[OptionalValidator()])
    target_molarity = FloatField("Target Molarity", validators=[OptionalValidator()])
    total_volume_ul = FloatField("Total Volume", validators=[OptionalValidator()])


class LoadFlowCellForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/load_flow_cell-1.1.html"
    _form_label = "load_flow_cell_form"

    input_fields = FieldList(FormField(SubForm), min_entries=1)

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
        df["lane_molarity"] = df["original_qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        df["library_volume"] = None
        df["eb_volume"] = None

        for i, (idx, row) in enumerate(df.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]

            if pd.notna(row["total_volume_ul"]):
                entry.total_volume_ul.data = row["total_volume_ul"]
            else:
                entry.total_volume_ul.data = self.experiment.workflow.volume_target_ul

            if pd.notna(row["sequencing_qubit_concentration"]):
                entry.measured_qubit.data = row["sequencing_qubit_concentration"]

            if pd.notna(row["target_molarity"]):
                entry.target_molarity.data = row["target_molarity"]
                library_volume = entry.total_volume_ul.data * row["target_molarity"] / row["lane_molarity"]
                df.at[idx, "library_volume"] = library_volume
                df.at[idx, "eb_volume"] = entry.total_volume_ul.data - library_volume

        df["sequencing_molarity"] = df["sequencing_qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
        self._context["df"] = df
    
    def process_request(self) -> Response:
        df = db.get_experiment_lanes_df(self.experiment.id)

        if not self.validate():
            df["qubit_concentration"] = df.apply(lambda row: row["original_qubit_concentration"] if pd.isna(row["sequencing_qubit_concentration"]) else row["sequencing_qubit_concentration"], axis="columns")
            df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
            self._context["df"] = df
            return self.make_response()
        
        all_lanes_loaded = True
        for i, (_, row) in enumerate(df.iterrows()):
            entry = self.input_fields[i]
            
            if (lane := db.get_lane(row["id"])) is None:
                raise ValueError(f"Lane with id {row['id']} not found")
            
            lane.target_molarity = entry.target_molarity.data
            lane.total_volume_ul = entry.total_volume_ul.data
            lane.sequencing_qubit_concentration = entry.measured_qubit.data
            if (lane.total_volume_ul is not None) and (lane.target_molarity is not None) and (lane.original_molarity is not None):
                lane.library_volume_ul = lane.total_volume_ul * lane.target_molarity / lane.original_molarity  # type: ignore
            lane = db.update_lane(lane)
            all_lanes_loaded = all_lanes_loaded and lane.is_loaded()

        if all_lanes_loaded:
            self.experiment.status = ExperimentStatus.LOADED
            self.experiment = db.update_experiment(self.experiment)

        flash("Saved!", "success")
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=self.experiment.id))
