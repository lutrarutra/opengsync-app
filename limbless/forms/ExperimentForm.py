from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length, ValidationError
from flask_login import current_user

from ..db import db_handler


class ExperimentForm(FlaskForm):
    flowcell = StringField("Flowcell", validators=[DataRequired(), Length(min=3, max=64)])
