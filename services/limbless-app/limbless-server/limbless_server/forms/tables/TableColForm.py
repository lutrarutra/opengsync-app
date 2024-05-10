from wtforms import StringField, BooleanField
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, Optional as OptionalValidator


class TableColForm(FlaskForm):
    column_name = StringField(validators=[DataRequired()])
    sort_by_descending = BooleanField(validators=[OptionalValidator()])
    query = StringField(validators=[OptionalValidator()])
    id_filter = StringField(validators=[OptionalValidator()])