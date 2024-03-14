from typing import Any, Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length

from limbless_db import models
from limbless_db.categories import SequencingStatus, ReadType
from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm


class SeqRunForm(HTMXFlaskForm):
    _template_path = "forms/seq_run.html"
    _form_label = "seq_run_form"

    experiment_name = StringField("Experiment Name", validators=[DataRequired(), Length(min=3, max=models.SeqRun.experiment_name.type.length)])   # type: ignore
    status = SelectField("Status", choices=SequencingStatus.as_selectable(), validators=[DataRequired()], coerce=int)  # type: ignore

    run_folder = StringField("Run Folder", validators=[DataRequired(), Length(min=1, max=models.SeqRun.run_folder.type.length)])  # type: ignore
    flowcell_id = StringField("Flowcell ID", validators=[DataRequired(), Length(min=1, max=models.SeqRun.flowcell_id.type.length)])  # type: ignore
    read_type = SelectField("Read Type", choices=models.ReadType.as_selectable(), validators=[DataRequired()], coerce=int)  # type: ignore
    rta_version = StringField("RTA Version", validators=[DataRequired(), Length(min=1, max=models.SeqRun.rta_version.type.length)])  # type: ignore
    recipe_version = StringField("Recipe Version", validators=[DataRequired(), Length(min=1, max=models.SeqRun.recipe_version.type.length)])  # type: ignore
    side = StringField("Side", validators=[DataRequired(), Length(min=1, max=models.SeqRun.side.type.length)])  # type: ignore
    flowcell_mode = StringField("Flowcell Mode", validators=[DataRequired(), Length(min=1, max=models.SeqRun.flowcell_mode.type.length)])  # type: ignore

    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[DataRequired()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[DataRequired()])

    def __init__(self, formdata: Optional[dict[str, Any]] = None, seq_run: Optional[models.SeqRun] = None):
        super().__init__(formdata=formdata)
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

        return True
    
    def create_seq_run(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        seq_run = db.create_seq_run(
            experiment_name=self.experiment_name.data,  # type: ignore
            status=SequencingStatus.get(int(self.status.data)),
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

        flash(f"SeqRun {seq_run.id} created successfully", "success")
        return make_response(
            redirect=url_for("")
        )
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        if (_ := context.get("seq_run")) is None:
            return self.create_seq_run(**context)
        
        raise NotImplementedError("Editing SeqRun is not yet implemented")



