from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length, ValidationError

from ..db import db_handler


class ExperimentForm(FlaskForm):
    name = StringField("Experiment Name", validators=[DataRequired(), Length(min=6, max=64)])
    flowcell = StringField("Flowcell", validators=[DataRequired(), Length(min=3, max=64)])

    def validate_name(self, name):
        if db_handler.get_experiment_by_name(name.data):
            raise ValidationError("Experiment name already exists.")
