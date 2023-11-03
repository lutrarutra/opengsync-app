from typing import Literal

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, BooleanField, EmailField
from wtforms.validators import DataRequired, Length, Optional, Email

from .. import logger
from ..categories import LibraryType
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession


class SelectLibraryForm(FlaskForm):
    library = IntegerField("Library", validators=[DataRequired()])


class LibraryForm(FlaskForm):
    _choises = LibraryType.as_selectable()
    name = StringField("Library Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    library_type = SelectField(
        "Library Type", choices=_choises,
        validators=[DataRequired()]
    )

    is_premade_library = BooleanField(
        "Is premade library", default=False,
        description="Check this if this if the library is premade library."
    )

    current_user_is_library_contact = BooleanField(
        "I prepared the libraries", default=True,
    )

    library_contact_name = StringField(
        "Library Contact Person Name", validators=[Optional(), Length(max=128)],
        description="Name of the library contact person"
    )

    library_contact_email = EmailField(
        "Library Contact Person Email", validators=[Optional(), Email(), Length(max=128)],
        description="E-Mail address of the library contact person"
    )

    library_contact_phone = StringField(
        "Library Contact Person Phone", validators=[Optional(), Length(max=16)],
        description="Phone number of the library contact person"
    )

    library_contact_insider = IntegerField("Select Technician", validators=[Optional()])

    index_kit = IntegerField("Index Kit", validators=[Optional()])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        library_id: int | None = None,
    ) -> tuple[bool, "LibraryForm"]:

        validated = self.validate()
        if self.is_premade_library.data:
            if not self.index_kit.data:
                self.index_kit.errors = ("Index kit is required for premade libraries.",)
                validated = False
            if not self.library_contact_email.data:
                self.library_contact_email.errors = ("Library contact email is required.",)
                validated = False
            if not self.library_contact_name.data:
                self.library_contact_name.errors = ("Library contact name is required.",)
                validated = False

        if not validated:
            return False, self
        
        with DBSession(db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
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

            if not self.is_premade_library.data:
                if self.index_kit.data is not None:
                    self.index_kit.errors = ("Index kit should not be selected for raw libraries.",)
                    validated = False
            else:
                if self.index_kit.data is None:
                    self.index_kit.errors = ("Index kit is required for non raw libraries.",)
                    validated = False
                else:
                    index_kit = session.get_index_kit(self.index_kit.data)
                    if (raw_library_type_id := self.library_type.data) is None:
                        self.library_type.errors = ("Library type is required.",)
                        validated = False
                    else:
                        try:
                            library_type_id = int(raw_library_type_id)
                        except ValueError:
                            self.library_type.errors = ("Invalid library type.",)
                            return False, self
                        try:
                            library_type = LibraryType.get(library_type_id)
                        except ValueError:
                            self.library_type.errors = ("Invalid library type.",)
                            return False, self

                        _library_types_ids = [library_type.id for library_type in index_kit.library_type_ids]
                        logger.debug(_library_types_ids)
                        logger.debug(library_type_id)
                        if library_type_id not in _library_types_ids:
                            self.library_type.errors = (
                                f"Library type '{library_type.name}' is not supported by the selected index kit.",
                            )
                            validated = False

        return validated, self
