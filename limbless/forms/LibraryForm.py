from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FieldList, FormField, TextAreaField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import DataRequired, Length,ValidationError

from .. import models
from ..db import db_handler

class LibraryForm(FlaskForm):    
    name = StringField("Library Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])
    
    library_type = SelectField(
        "Library Type", choices=models.LibraryType.to_tuple(),
        validators=[DataRequired()]
    )

    def validate_name(self, name):
        if db_handler.get_library_by_name(name.data):
            raise ValidationError("Library name already exists.")