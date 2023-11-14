from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import db, models, logger
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession
from ...categories import LibraryType
from .TableDataForm import TableDataForm


class LibrarySubForm(FlaskForm):
    raw_category = StringField("Raw Type", validators=[OptionalValidator()])
    category = SelectField("Library Type", choices=LibraryType.as_selectable(), validators=[DataRequired()])


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
        logger.debug(library_types)
        # for library_type in library_types:
        #     self.input_fields.append_entry()

        self.set_df(df)
        return {
            "categories": library_types,
            "selected": [],
        }

    def parse(self) -> pd.DataFrame:
        df = self.get_df()
        df.loc[df["library_type"].isna(), "library_type"] = "__none__"
        library_types = df["library_type"].unique()
        library_types = [library_type if library_type and not pd.isna(library_type) else None for library_type in library_types]

        df["library_type_id"] = None
        for i, library_type in enumerate(library_types):
            df.loc[df["library_type"] == library_type, "library_type_id"] = int(self.input_fields.entries[i].category.data)
        
        df["library_type"] = df["library_type_id"].apply(lambda x: LibraryType.get(x).value.name)
        self.data.data = df.to_csv(sep="\t", index=False, header=True)
        return df