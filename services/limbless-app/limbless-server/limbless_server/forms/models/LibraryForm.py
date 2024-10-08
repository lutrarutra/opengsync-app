from typing import Any, Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import LibraryType, GenomeRef
from ... import db, logger  # noqa: F401
from ..HTMXFlaskForm import HTMXFlaskForm


class LibraryForm(HTMXFlaskForm):
    _template_path = "forms/library.html"
    _form_label = "library_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=3, max=models.Library.name.type.length)])
    # adapter = StringField("Adapter", validators=[OptionalValidator(), Length(min=1, max=models.Library.adapter.type.length)])
    library_type = SelectField("Library Type", choices=LibraryType.as_selectable(), coerce=int)
    genome = SelectField("Reference Genome", choices=GenomeRef.as_selectable(), coerce=int)
    index_1 = StringField("Index 1 (i7)", validators=[OptionalValidator(), Length(min=1, max=models.Barcode.sequence.type.length)])
    index_2 = StringField("Index 2 (i5)", validators=[OptionalValidator(), Length(min=1, max=models.Barcode.sequence.type.length)])
    # index_3 = StringField("Index 3", validators=[OptionalValidator(), Length(min=1, max=models.Library.index_3_sequence.type.length)])
    # index_4 = StringField("Index 4", validators=[OptionalValidator(), Length(min=1, max=models.Library.index_4_sequence.type.length)])

    def __init__(self, formdata: Optional[dict[str, Any]] = None, library: Optional[models.Library] = None):
        super().__init__(formdata=formdata)
        if library is not None:
            self.__fill_form(library)

    def __fill_form(self, library: models.Library):
        self.name.data = library.name
        self.library_type.data = library.type_id
        self.genome.data = library.genome_ref_id
        # self.index_1.data = library.index_1_sequence
        # self.index_2.data = library.
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        library: models.Library = context["library"]

        library.name = self.name.data   # type: ignore
        library.type = LibraryType.get(int(self.library_type.data))
        library.genome_ref = GenomeRef.get(self.genome.data)
        # library.index_1_sequence = self.index_1.data.strip() if self.index_1.data and self.index_1.data.strip() else None
        # library.index_2_sequence = self.index_2.data.strip() if self.index_2.data and self.index_2.data.strip() else None

        library = db.update_library(library)
        
        flash(f"Updated library '{library.name}'.", "success")

        return make_response(
            redirect=url_for("libraries_page.library_page", library_id=library.id),
        )