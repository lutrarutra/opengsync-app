from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, StringField, SelectField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from limbless_db.categories import GenomeRef

from .... import db, tools
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from .LibraryMappingForm import LibraryMappingForm


class GenomeRefSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    genome = SelectField("Select Reference Genome", choices=GenomeRef.as_selectable(), validators=[DataRequired()], coerce=int)


# 4. Select genome for libraries
class GenomeRefMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-3.html"

    input_fields = FieldList(FormField(GenomeRefSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()
            
        df: pd.DataFrame = data["library_table"]  # type: ignore
        df["duplicate"] = False

        genomes = df["genome"].unique().tolist()

        for i, raw_genome_name in enumerate(genomes):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields.entries[i]
            entry.raw_label.data = raw_genome_name
            
            if (selected_id := entry.genome.data) is not None:
                selected_genome = GenomeRef.get(selected_id)
            else:
                if raw_genome_name is None or pd.isna(raw_genome_name):
                    selected_genome = None
                else:
                    _genomes = [(e.name, id) for id, e in GenomeRef.as_tuples()]
                    
                    if (id := tools.mapstr(raw_genome_name, _genomes, cutoff=0.3)) is not None:
                        selected_genome = GenomeRef.get(id)
                    
                        entry.genome.data = selected_genome.id
            
        data["library_table"] = df
        self.update_data(data)

        return {}
    
    def __parse(self) -> dict[str, pd.DataFrame | dict]:
        data = self.get_data()

        genome_id_mapping = {}
        genomes = data["library_table"]["genome"].unique()
    
        for i, genome in enumerate(genomes):
            genome_id_mapping[genome] = self.input_fields.entries[i].genome.data
        
        data["library_table"]["genome_id"] = data["library_table"]["genome"].map(genome_id_mapping)
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
