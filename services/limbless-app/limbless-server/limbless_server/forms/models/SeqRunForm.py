from typing import Any, Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length

from limbless_db import models
from limbless_db.categories import ExperimentStatus, ReadType, ExperimentStatus
from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm


class SeqRunForm(HTMXFlaskForm):
    _template_path = "forms/seq_run.html"
    _form_label = "seq_run_form"

    experiment_name = StringField("Experiment Name", validators=[DataRequired(), Length(min=3, max=models.SeqRun.experiment_name.type.length)])   # type: ignore
    status = SelectField("Status", choices=ExperimentStatus.as_selectable(), validators=[DataRequired()], coerce=int)  # type: ignore

    run_folder = StringField("Run Folder", validators=[DataRequired(), Length(min=1, max=models.SeqRun.run_folder.type.length)])  # type: ignore
    flowcell_id = StringField("Flowcell ID", validators=[DataRequired(), Length(min=1, max=models.SeqRun.flowcell_id.type.length)])  # type: ignore
    read_type = SelectField("Read Type", choices=ReadType.as_selectable(), validators=[DataRequired()], coerce=int)  # type: ignore
    rta_version = StringField("RTA Version", validators=[DataRequired(), Length(min=1, max=models.SeqRun.rta_version.type.length)])  # type: ignore
    recipe_version = StringField("Recipe Version", validators=[DataRequired(), Length(min=1, max=models.SeqRun.recipe_version.type.length)])  # type: ignore
    side = StringField("Side", validators=[DataRequired(), Length(min=1, max=models.SeqRun.side.type.length)])  # type: ignore
    flowcell_mode = StringField("Flowcell Mode", validators=[DataRequired(), Length(min=1, max=models.SeqRun.flowcell_mode.type.length)])  # type: ignore

    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[DataRequired()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[DataRequired()])

    def __init__(self, formdata: Optional[dict[str, Any]] = None, seq_run: Optional[models.SeqRun] = None, csrf_enabled: bool = True):
        super().__init__(formdata=formdata, meta={"csrf": csrf_enabled})
        if seq_run is not None:
            self.__fill_form(seq_run)

    def __fill_form(self, seq_run: models.SeqRun):
        self.experiment_name.data = seq_run.experiment_name
        self.status.data = seq_run.status_id
        self.run_folder.data = seq_run.run_folder
        self.flowcell_id.data = seq_run.flowcell_id
        self.read_type.data = seq_run.read_type_id
        self.rta_version.data = seq_run.rta_version
        self.recipe_version.data = seq_run.recipe_version
        self.side.data = seq_run.side
        self.flowcell_mode.data = seq_run.flowcell_mode
        self.r1_cycles.data = seq_run.r1_cycles
        self.r2_cycles.data = seq_run.r2_cycles
        self.i1_cycles.data = seq_run.i1_cycles
        self.i2_cycles.data = seq_run.i2_cycles

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        try:
            ExperimentStatus.get(int(self.status.data))
        except ValueError:
            self.status.errors = ("Invalid status",)
            return False
        
        if db.get_seq_run(experiment_name=self.experiment_name.data) is not None:
            self.experiment_name.errors = ("experiment_name not unique",)
            return False

        return True
    
    def create_seq_run(self) -> models.SeqRun:
        seq_run = db.create_seq_run(
            experiment_name=self.experiment_name.data,  # type: ignore
            status=ExperimentStatus.get(int(self.status.data)),
            run_folder=self.run_folder.data,  # type: ignore
            flowcell_id=self.flowcell_id.data,  # type: ignore
            read_type=ReadType.get(int(self.read_type.data)),
            rta_version=self.rta_version.data,  # type: ignore
            recipe_version=self.recipe_version.data,  # type: ignore
            side=self.side.data,  # type: ignore
            flowcell_mode=self.flowcell_mode.data,  # type: ignore
            r1_cycles=self.r1_cycles.data,  # type: ignore
            r2_cycles=self.r2_cycles.data,  # type: ignore
            i1_cycles=self.i1_cycles.data,  # type: ignore
            i2_cycles=self.i2_cycles.data  # type: ignore
        )

        if (experiment := db.get_experiment(name=seq_run.experiment_name)) is not None:
            if seq_run.status != experiment.status:
                experiment.status_id = seq_run.status.id
                experiment = db.update_experiment(experiment)

        return seq_run
    
    def update_seq_run(self, seq_run: models.SeqRun) -> models.SeqRun:
        seq_run.status_id = int(self.status.data)
        seq_run.run_folder = self.run_folder.data  # type: ignore
        seq_run.flowcell_id = self.flowcell_id.data  # type: ignore
        seq_run.read_type_id = int(self.read_type.data)  # type: ignore
        seq_run.rta_version = self.rta_version.data  # type: ignore
        seq_run.recipe_version = self.recipe_version.data  # type: ignore
        seq_run.side = self.side.data  # type: ignore
        seq_run.flowcell_mode = self.flowcell_mode.data  # type: ignore
        seq_run.r1_cycles = self.r1_cycles.data  # type: ignore
        seq_run.r2_cycles = self.r2_cycles.data  # type: ignore
        seq_run.i1_cycles = self.i1_cycles.data  # type: ignore
        seq_run.i2_cycles = self.i2_cycles.data  # type: ignore

        return db.update_seq_run(seq_run)
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        if (seq_run := context.get("seq_run")) is None:
            seq_run = self.create_seq_run()
            flash(f"SeqRun {seq_run.id} created successfully", "success")
            return make_response(
                redirect=url_for("")
            )
        
        seq_run = self.update_seq_run(seq_run)
        flash(f"SeqRun {seq_run.id} edited successfully", "success")
        return make_response(
            redirect=url_for("")
        )



