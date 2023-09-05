from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError

from ..db import db_handler


class ProjectForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=64)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=1, max=1024)])

    def validate_name(self, name):
        if db_handler.get_project_by_name(name.data):
            raise ValidationError("Project name already exists.")
