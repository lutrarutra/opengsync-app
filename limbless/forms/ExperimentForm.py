from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, NumberRange, Optional as OptionalValidator
from flask_login import current_user

from ..core.DBHandler import DBHandler
from ..categories import FlowCellType


class ExperimentForm(FlaskForm):
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

    def custom_validate(self) -> tuple[bool, "ExperimentForm"]:
        
        validated = self.validate()
        if not validated:
            return False, self

        # TODO: check if lane is already in use when removing lanes
        return True, self
