from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import DataRequired, Length, ValidationError
from flask_login import current_user

from ..db import db_handler
from ..core.DBHandler import DBHandler


class ExperimentForm(FlaskForm):
    flowcell = StringField("Flowcell", validators=[DataRequired(), Length(min=3, max=64)])

    sequencer = IntegerField("Sequencer", validators=[DataRequired()])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        experiment_id: int | None = None,
    ) -> tuple[bool, "ExperimentForm"]:
        
        validated = self.validate()
        if not validated:
            return False, self

        return True, self
