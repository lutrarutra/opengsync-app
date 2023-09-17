from typing import Literal

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional

from .. import logger
from ..categories import LibraryType
from ..core.DBHandler import DBHandler


class LibraryForm(FlaskForm):
    _choises = LibraryType.as_selectable()
    name = StringField("Library Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    library_type = SelectField(
        "Library Type", choices=_choises,
        validators=[DataRequired()]
    )

    is_raw_library = BooleanField(
        "Is raw library", default=True,
        description="Check this if this if the library is not sequencing ready."
    )

    index_kit = IntegerField("Index Kit", validators=[Optional()])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        library_id: int | None = None,
    ) -> tuple[bool, "LibraryForm"]:

        validated = self.validate()
        if not validated:
            return False, self

        db_handler.open_session()
        if (user := db_handler.get_user(user_id)) is None:
            logger.error(f"User with id {user_id} does not exist.")
            db_handler.close_session()
            return False, self

        user_libraries = user.libraries

        # Creating new library
        if library_id is None:
            if self.name.data in [library.name for library in user_libraries]:
                self.name.errors = ("You already have a library with this name.",)
                validated = False

        # Editing existing library
        else:
            for library in user_libraries:
                if library.name == self.name.data:
                    if library.id != library_id and library.owner_id == user_id:
                        self.name.errors = ("You already have a library with this name.",)
                        validated = False

        if self.is_raw_library.data:
            if self.index_kit.data is not None:
                self.index_kit.errors = ("Index kit should not be selected for raw libraries.",)
                validated = False
        else:
            if self.index_kit.data is None:
                self.index_kit.errors = ("Index kit is required for non raw libraries.",)
                validated = False

        db_handler.close_session()

        return validated, self
