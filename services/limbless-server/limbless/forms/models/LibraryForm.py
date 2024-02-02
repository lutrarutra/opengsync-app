from typing import Any, Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length
from wtforms.validators import Optional as OptionalValidator

from ...categories import LibraryType
from ... import db, logger, models
from ..HTMXFlaskForm import HTMXFlaskForm


class LibraryForm(HTMXFlaskForm):
    _template_path = "forms/library.html"
    _form_label = "library_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=3, max=64)])
    adapter = StringField("Adapter", validators=[OptionalValidator(), Length(min=1, max=32)])
    library_type = SelectField("Library Type", choices=LibraryType.as_selectable(), validators=[DataRequired()])
    index_1 = StringField("Index 1 (i7)", validators=[DataRequired(), Length(min=1, max=32)])
    index_2 = StringField("Index 2 (i5)", validators=[OptionalValidator(), Length(min=1, max=32)])
    index_3 = StringField("Index 3", validators=[OptionalValidator(), Length(min=1, max=32)])
    index_4 = StringField("Index 4", validators=[OptionalValidator(), Length(min=1, max=32)])

    def __init__(self, formdata: Optional[dict[str, Any]] = None, library: Optional[models.Library] = None):
        super().__init__(formdata=formdata)
        if library is not None:
            self.__fill_form(library)

    def __fill_form(self, library: models.Library):
        self.name.data = library.name
        self.adapter.data = library.adapter
        self.library_type.data = library.type_id
        self.index_1.data = library.index_1_sequence
        self.index_2.data = library.index_2_sequence
        self.index_3.data = library.index_3_sequence
        self.index_4.data = library.index_4_sequence

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        try:
            LibraryType.get(int(self.library_type.data))
        except ValueError:
            self.library_type.errors = ("Invalid library type.",)
            return False

        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        library: models.Library = context["library"]

        library_type = LibraryType.get(int(self.library_type.data))

        library.name = self.name.data
        library.type_id = library_type.value.id
        library.index_1_sequence = self.index_1.data
        library.index_2_sequence = self.index_2.data
        library.index_3_sequence = self.index_3.data
        library.index_4_sequence = self.index_4.data
        library.adapter = self.adapter.data

        library = db.db_handler.update_library(library)
        
        logger.debug(f"Updated library '{library.name}'.")
        flash(f"Updated library '{library.name}'.", "success")

        return make_response(
            redirect=url_for("libraries_page.library_page", library_id=library.id),
        )