import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models

from .. import logger, db
from ..tools.spread_sheet_components import TextColumn, SpreadSheetColumn
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput


class LibraryPropertiesForm(HTMXFlaskForm):
    _template_path = "forms/library-properties-table.html"

    predefined_columns: list[SpreadSheetColumn] = [
        TextColumn("property", "Property", 300, max_length=models.SampleAttribute.MAX_NAME_LENGTH, required=True, read_only=False),
        TextColumn("value", "Value", 500, max_length=1024, required=True, read_only=False),
    ]

    def __init__(self, library: models.Library, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.library = library
        self._context["library"] = library

        df = pd.DataFrame(library.properties.items() if library.properties else {}, columns=["property", "value"])

        self.spreadsheet = SpreadsheetInput(
            columns=LibraryPropertiesForm.predefined_columns, csrf_token=self._csrf_token,
            post_url=url_for('libraries_htmx.edit_properties', library_id=library.id),
            formdata=formdata, allow_new_rows=True, allow_new_cols=False, df=df
        )

    def validate(self) -> bool:
        if not super().validate() or self.formdata is None:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        
        self.df = df

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.library.properties is None:
            self.library.properties = {}

        for _, row in self.df.iterrows():
            self.library.properties[row["property"]] = row["value"]

        for prop in list(self.library.properties.keys()):
            if prop not in self.df["property"].values:
                del self.library.properties[prop]

        db.libraries.update(self.library)

        flash("Changes Saved!", "success")
        return make_response(redirect=url_for("libraries_page.library", library_id=self.library.id))
