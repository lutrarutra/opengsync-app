from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import IntegerField
from wtforms.validators import NumberRange

from opengsync_db import models
from ..HTMXFlaskForm import HTMXFlaskForm

from ... import db, logger


class EditExperimentCyclesForm(HTMXFlaskForm):
    _template_path = "workflows/edit_experiment_cycles.html"
    
    cycles_r1 = IntegerField("R1 Cycles", validators=[NumberRange(min=0)])
    cycles_r2 = IntegerField("R2 Cycles", validators=[NumberRange(min=0)])
    cycles_i1 = IntegerField("I1 Cycles", validators=[NumberRange(min=0)])
    cycles_i2 = IntegerField("I2 Cycles", validators=[NumberRange(min=0)])

    def __init__(self, current_user: models.User, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.form_type = "create" if experiment is None else "edit"
        self.experiment = experiment
        self.current_user = current_user
        self._context["experiment"] = experiment

    def prepare(self):
        logger.debug(f"Preparing form with experiment: {self.experiment}")
        self.cycles_r1.data =  self.experiment.r1_cycles
        self.cycles_r2.data =  self.experiment.r2_cycles
        self.cycles_i1.data =  self.experiment.i1_cycles
        self.cycles_i2.data =  self.experiment.i2_cycles

    def validate(self) -> bool:
        if (validated := super().validate()) is False:
            logger.debug(self.cycles_r1.data)
            return False
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.experiment.r1_cycles = self.cycles_r1.data
        self.experiment.r2_cycles = self.cycles_r2.data
        self.experiment.i1_cycles = self.cycles_i1.data
        self.experiment.i2_cycles = self.cycles_i2.data

        db.experiments.update(self.experiment)

        flash(f"Changes Saved!.", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id, tab="checklist-tab"))
    