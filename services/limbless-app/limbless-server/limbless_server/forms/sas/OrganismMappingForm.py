from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, StringField, SelectField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from limbless_db.categories import GenomeRef

from ... import db, tools
from ..TableDataForm import TableDataForm
from ..HTMXFlaskForm import HTMXFlaskForm
from .LibraryMappingForm import LibraryMappingForm


class OrganismSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    organism = SelectField("Select Organism", choices=GenomeRef.as_selectable(), validators=[DataRequired()], coerce=int)


# 4. Select organism for samples
class OrganismMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "components/popups/seq_request/sas-3.html"

    input_fields = FieldList(FormField(OrganismSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()
            
        df: pd.DataFrame = data["library_table"]  # type: ignore
        df["duplicate"] = False

        organisms = df["organism"].unique().tolist()

        for i, raw_organism_name in enumerate(organisms):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields.entries[i]
            entry.raw_label.data = raw_organism_name
            
            if (selected_id := entry.organism.data) is not None:
                selected_organism = Organism.get(selected_id)
            else:
                if raw_organism_name is None or pd.isna(raw_organism_name):
                    selected_organism = None
                else:
                    organisms = [(e.name, id) for id, e in Organism.as_tuples()] + [(e.description, id) for id, e in Organism.as_tuples() if e.description is not None]
                    
                    if (id := tools.mapstr(raw_organism_name, organisms, cutoff=0.3)) is not None:
                        selected_organism = Organism.get(id)
                    
                        entry.organism.data = selected_organism.id
            
        data["library_table"] = df
        self.update_data(data)

        return {}
    
    def __parse(self) -> dict[str, pd.DataFrame | dict]:
        data = self.get_data()

        organism_id_mapping = {}
        organisms = data["library_table"]["organism"].unique()
    
        for i, organism in enumerate(organisms):
            organism_id_mapping[organism] = self.input_fields.entries[i].organism.data
        
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
