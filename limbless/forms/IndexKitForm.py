from typing import Literal

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional

from ..core.DBHandler import DBHandler


class IndexKitForm(FlaskForm):
    name = StringField("Index Kit Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        index_kit_id: int | None = None,
    ) -> tuple[bool, "IndexKitForm"]:

        validated = self.validate()
        if not validated:
            return False, self

        return validated, self