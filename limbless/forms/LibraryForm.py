from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import DataRequired, Length,ValidationError

from .. import models
from ..core import categories
from ..db import db_handler

class LibraryForm(FlaskForm):    
    name = StringField("Library Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])
    
    library_type = SelectField(
        "Library Type", choices=categories.LibraryType.as_tuples(),
        validators=[DataRequired()]
    )

    index_kit = IntegerField("Index Kit", validators=[DataRequired()])
    index_kit_search = StringField("Index Kit")

    def validate_name(self, name):
        if db_handler.get_library_by_name(name.data):
            raise ValidationError("Library name already exists.")