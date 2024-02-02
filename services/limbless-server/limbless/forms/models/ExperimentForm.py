from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, IntegerField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, NumberRange

from ..HTMXFlaskForm import HTMXFlaskForm
from ...categories import FlowCellType
from ... import db, logger


class ExperimentForm(HTMXFlaskForm):
    _template_path = "forms/experiment.html"

    sequencer = IntegerField("Sequencer", validators=[DataRequired()])
    flowcell_type = SelectField(
        "Flowcell Type", choices=FlowCellType.as_selectable(),
        validators=[DataRequired()],
        description="Type of flowcell to use for sequencing."
    )
    flowcell = StringField("Flowcell ID", validators=[DataRequired(), Length(min=3, max=64)])
    num_lanes = IntegerField("Number of Lanes", default=1, validators=[DataRequired(), NumberRange(min=1, max=8)])
    
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[])

    current_user_is_seq_person = BooleanField("I am the sequencing person", default=True)
    sequencing_person = IntegerField("Sequencing Person", validators=[DataRequired()])

    def validate(self) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        # TODO: check if lane is already in use when removing lanes
        return validated

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        experiment_id = context["experiment_id"]
    
        experiment = db.db_handler.update_experiment(
            experiment_id=experiment_id,
            flowcell=self.flowcell.data,
            r1_cycles=self.r1_cycles.data,
            r2_cycles=self.r2_cycles.data,
            i1_cycles=self.i1_cycles.data,
            i2_cycles=self.i2_cycles.data,
            num_lanes=self.num_lanes.data,
            sequencer_id=self.sequencer.data,
            sequencing_person_id=self.sequencing_person.data,
        )

        logger.debug(f"Edited experiment on flowcell '{experiment.flowcell}'")
        flash(f"Edited experiment on flowcell '{experiment.flowcell}'.", "success")

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))