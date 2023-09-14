from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms.validators import DataRequired


class SelectLibraryForm(FlaskForm):
    library = IntegerField("Library", validators=[DataRequired()])