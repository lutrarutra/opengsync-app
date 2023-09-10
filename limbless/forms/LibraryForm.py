from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length, ValidationError


from .. import categories
from ..db import db_handler


class LibraryForm(FlaskForm):
    _choises = categories.LibraryType.as_selectable()
    name = StringField("Library Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    library_type = SelectField(
        "Library Type", choices=_choises,
        validators=[DataRequired()]
    )

    index_kit = IntegerField("Index Kit", validators=[DataRequired()])

    def validate_name(self, name):
        if db_handler.get_library_by_name(name.data):
            raise ValidationError("Library name already exists.")
