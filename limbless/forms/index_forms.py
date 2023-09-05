from flask_wtf import FlaskForm
from wtforms import StringField, SelectField

from wtforms.validators import DataRequired


class SCRNAIndexForm(FlaskForm):
    adapter = StringField("Adapter", validators=[DataRequired()])
    adapter_search = StringField("Adapter")

    workflow = SelectField("Workflow", choices=[])
