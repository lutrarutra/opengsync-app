from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, TextAreaField, IntegerField, BooleanField, StringField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import tools, models, db, logger
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession
from .TableDataForm import TableDataForm


class OrganismSubForm(FlaskForm):
    raw_category = StringField("Raw Label", validators=[OptionalValidator()])
    category = IntegerField("Organism", validators=[DataRequired()], default=None)


# 4. Select organism for samples
class OrganismMappingForm(TableDataForm):
    input_fields = FieldList(FormField(OrganismSubForm), min_entries=1)

    def prepare(self, seq_request_id: int, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()
            
        df["duplicate"] = False

        self.set_df(df)
        organisms = sorted(df["organism"].unique())
        selected: list[Optional[str]] = []

        for i, raw_organism_name in enumerate(organisms):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields.entries[i]
            
            if (selected_id := entry.category.data) is not None:
                selected_organism = db.db_handler.get_organism(selected_id)
            else:
                if organisms[i] is None:
                    selected_organism = None
                else:
                    if raw_organism_name is None or pd.isna(raw_organism_name):
                        raw_organism_name = ""
                    selected_organism = next(iter(db.db_handler.query_organisms(word=raw_organism_name, limit=1)), None)
                    entry.category.data = selected_organism.id if selected_organism is not None else None

            selected.append(selected_organism.to_str() if selected_organism is not None else None)

        return {
            "categories": organisms,
            "selected": selected,
        }

    def custom_validate(self, db_handler: DBHandler):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self