from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, ValidationError, NumberRange
from wtforms.validators import Optional as OptionalValidator

from ..core.DBHandler import DBHandler
from ..categories import LibraryType


class EditLibraryForm(FlaskForm):
    adapter = StringField("Adapter", validators=[OptionalValidator(), Length(min=1, max=32)])
    library_type = SelectField("Library Type", choices=LibraryType.as_selectable(), validators=[DataRequired()])
    index_1 = StringField("Index 1 (i7)", validators=[DataRequired(), Length(min=1, max=32)])
    index_2 = StringField("Index 2 (i5)", validators=[OptionalValidator(), Length(min=1, max=32)])
    index_3 = StringField("Index 3", validators=[OptionalValidator(), Length(min=1, max=32)])
    index_4 = StringField("Index 4", validators=[OptionalValidator(), Length(min=1, max=32)])

    def custom_validate(
        self, db_handler: DBHandler 
    ) -> tuple[bool, "EditLibraryForm"]:
        validated = self.validate()
        if not validated:
            return False, self

        return True, self