from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms.validators import DataRequired, ValidationError


class RunForm(FlaskForm):
    lane = IntegerField("Lane", default=1, validators=[DataRequired()])
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[DataRequired()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[DataRequired()])

    def validate_lane(self, lane):
        if lane.data < 1:
            raise ValidationError("Lane must be greater than 0.")
