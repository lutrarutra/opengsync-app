from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, ValidationError, NumberRange
from flask_login import current_user

from ..core.DBHandler import DBHandler


class ExperimentForm(FlaskForm):
    flowcell = StringField("Flowcell", validators=[DataRequired(), Length(min=3, max=64)])
    sequencer = IntegerField("Sequencer", validators=[DataRequired()])
    
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[])
    num_lanes = IntegerField("Number of Lanes", default=1, validators=[DataRequired(), NumberRange(min=1, max=8)])

    current_user_is_seq_person = BooleanField("I am the sequencing person", default=True)
    sequencing_person = IntegerField("Sequencing Person", validators=[DataRequired()])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        experiment_id: int | None = None,
    ) -> tuple[bool, "ExperimentForm"]:
        
        validated = self.validate()
        if not validated:
            return False, self

        # TODO: check if lane is already in use when removing lanes
        return True, self
