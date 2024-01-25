from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, TextAreaField, IntegerField, BooleanField, StringField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import tools, models, db, logger
from .TableDataForm import TableDataForm


class OrganismSubForm(FlaskForm):
    raw_category = StringField("Raw Label", validators=[OptionalValidator()])
    category = IntegerField("Organism", validators=[DataRequired()], default=None)


# 4. Select organism for samples
class OrganismMappingForm(TableDataForm):
    input_fields = FieldList(FormField(OrganismSubForm), min_entries=1)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.data
            
        df = data["library_table"]
        df["duplicate"] = False

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
                    if raw_organism_name is None or pd.isna(raw_organism_name) or raw_organism_name.strip().lower() == "organism":
                        selected_organism = None
                    else:
                        selected_organism = next(iter(db.db_handler.query_organisms(word=raw_organism_name, limit=1)), None)

                    entry.category.data = selected_organism.id if selected_organism is not None else None

            selected.append(selected_organism.to_str() if selected_organism is not None else None)

        data["library_table"] = df
        self.update_data(data)

        return {
            "categories": organisms,
            "selected": selected,
        }
    
    def parse(self) -> dict[str, pd.DataFrame]:
        data = self.data

        organism_id_mapping = {}
        organisms = sorted(data["library_table"]["organism"].unique())
    
        for i, organism in enumerate(organisms):
            organism_id_mapping[organism] = self.input_fields.entries[i].category.data
        
        data["library_table"]["tax_id"] = data["library_table"]["organism"].map(organism_id_mapping)
        self.update_data(data)
        return data

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self