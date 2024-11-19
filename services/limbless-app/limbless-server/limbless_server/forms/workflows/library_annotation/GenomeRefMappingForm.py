from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, StringField, SelectField, TextAreaField
from wtforms.validators import Optional as OptionalValidator, Length

from limbless_db.categories import GenomeRef
from limbless_db import models

from .... import tools
from ...MultiStepForm import MultiStepForm
from .LibraryMappingForm import LibraryMappingForm


class GenomeRefSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    genome = SelectField("Select Reference Genome", choices=GenomeRef.as_selectable(), coerce=int)


# 4. Select genome for libraries
class GenomeRefMappingForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-3.html"

    input_fields = FieldList(FormField(GenomeRefSubForm), min_entries=1)
    custom_reference = TextAreaField("Custom Reference", validators=[OptionalValidator(), Length(max=models.Comment.text.type.length)], description="If the reference genome is not in the list, specify it here.")

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(self, dirname="library_annotation", uuid=uuid, formdata=formdata, previous_form=previous_form)
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        valid = super().validate()
        if not valid:
            return False

        for entry in self.input_fields.entries:
            if GenomeRef.CUSTOM.id == entry.genome.data and not self.custom_reference.data:
                self.custom_reference.errors = ("Custom reference must be specified if custom genome is selected.",)
                return False

        return True

    def prepare(self):
        library_table: pd.DataFrame = self.tables["library_table"]

        genomes = library_table["genome"].unique().tolist()

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
    
    def process_request(self) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response()
        
        genome_id_mapping = {}
        library_table: pd.DataFrame = self.tables["library_table"]
        genomes = library_table["genome"].unique()
    
        for i, genome in enumerate(genomes):
            genome_id_mapping[genome] = self.input_fields.entries[i].genome.data

        library_table["genome_id"] = library_table["genome"].map(genome_id_mapping)

        if self.custom_reference.data:
            if (comment_table := self.tables.get("comment_table")) is None:  # type: ignore
                comment_table = pd.DataFrame({
                    "context": ["custom_genome_reference"],
                    "text": [self.custom_reference.data]
                })
            else:
                comment_table = pd.concat([
                    comment_table,
                    pd.DataFrame({
                        "context": ["custom_genome_reference"],
                        "text": [self.custom_reference.data]
                    })
                ])
            self.add_table("comment_table", comment_table)
        
        self.update_table("library_table", library_table)

        library_mapping_form = LibraryMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        library_mapping_form.prepare()
        return library_mapping_form.make_response()
