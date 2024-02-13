from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, StringField
from wtforms.validators import Optional as OptionalValidator

from ... import db
from ..TableDataForm import TableDataForm

from ..HTMXFlaskForm import HTMXFlaskForm
from .LibraryMappingForm import LibraryMappingForm
from ..SearchBar import SearchBar


class OrganismSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    organism = FormField(SearchBar, label="Select Orgnanism")


# 4. Select organism for samples
class OrganismMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "components/popups/seq_request/sas-3.html"

    input_fields = FieldList(FormField(OrganismSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()
            
        df = data["library_table"]
        df["duplicate"] = False

        organisms = df["organism"].unique().tolist()

        for i, raw_organism_name in enumerate(organisms):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields.entries[i]
            entry.raw_label.data = raw_organism_name
            
            if (selected_id := entry.organism.selected.data) is not None:
                selected_organism = db.get_organism(selected_id)
            else:
                if raw_organism_name is None or pd.isna(raw_organism_name):
                    selected_organism = None
                else:
                    selected_organism = next(iter(db.query_organisms(word=raw_organism_name, limit=1)), None)
                    entry.organism.selected.data = selected_organism.id if selected_organism is not None else None
                    entry.organism.search_bar.data = selected_organism.search_name() if selected_organism is not None else None
            
        data["library_table"] = df
        self.update_data(data)

        return {}
    
    def __parse(self) -> dict[str, pd.DataFrame]:
        data = self.get_data()

        organism_id_mapping = {}
        organisms = sorted(data["library_table"]["organism"].unique())
    
        for i, organism in enumerate(organisms):
            organism_id_mapping[organism] = self.input_fields.entries[i].organism.selected.data
        
        data["library_table"]["tax_id"] = data["library_table"]["organism"].map(organism_id_mapping)
        self.update_data(data)
        return data
    
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response(**context)
        
        data = self.__parse()

        library_mapping_form = LibraryMappingForm(uuid=self.uuid)
        context = library_mapping_form.prepare(data) | context
        return library_mapping_form.make_response(**context)
