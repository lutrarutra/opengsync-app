from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import db, models, logger, tools
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession
from ...categories import LibraryType
from .TableDataForm import TableDataForm


class LibrarySubForm(FlaskForm):
    _similars = {
        "custom": 0,
        "gex": 1,
        "hto": 2,
        "atac": 3,
        "vdj-b": 5,
        "vdj-t": 6,
        "vdj-gd": 7,
        "vdj-t-gd": 7,
        "abc": 8,
        "crispr": 9
    }
    raw_category = StringField("Raw Type", validators=[OptionalValidator()])
    category = SelectField("Library Type", choices=LibraryType.as_selectable(), validators=[DataRequired()], default=None)


class LibraryMappingForm(TableDataForm):
    input_fields = FieldList(FormField(LibrarySubForm), min_entries=1)

    def custom_validate(self, db_handler: DBHandler):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self
    
    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()
        
        library_types = sorted(df["library_type"].unique().tolist())
        library_types = [library_type if library_type and not pd.isna(library_type) else "Library" for library_type in library_types]

        selected: list[Optional[int]] = []
        for i, library_type in enumerate(library_types):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields.entries[i]
            
            selected_library_type = None
            if (selected_id := entry.category.data) is not None:
                try:
                    selected_id = int(selected_id)
                    selected_library_type = LibraryType.get(selected_id)
                except ValueError:
                    selected_id = None

            else:
                if library_type is not None:
                    similars = tools.connect_similar_strings(LibraryType.as_selectable(), [library_type], similars=LibrarySubForm._similars, cutoff=0.2)
                    if (similar := similars[library_type]) is not None:
                        selected_library_type = LibraryType.get(similar)

            if selected_library_type is not None:
                entry.category.data = selected_library_type.value.id
                selected.append(selected_library_type.value.name)
            else:
                selected.append(None)

        self.set_df(df)
        return {
            "categories": library_types,
        }

    def parse(self) -> pd.DataFrame:
        df = self.get_df()
        df.loc[df["library_type"].isna(), "library_type"] = "Library"
        library_types = df["library_type"].unique()
        library_types = [library_type if library_type and not pd.isna(library_type) else None for library_type in library_types]

        df["library_type_id"] = None
        for i, library_type in enumerate(library_types):
            df.loc[df["library_type"] == library_type, "library_type_id"] = int(self.input_fields.entries[i].category.data)
        
        df["library_type"] = df["library_type_id"].apply(lambda x: LibraryType.get(x).value.name)
        self.set_df(df)
        return df