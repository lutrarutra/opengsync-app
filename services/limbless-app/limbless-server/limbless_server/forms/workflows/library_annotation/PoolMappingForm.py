from typing import Optional, TYPE_CHECKING

import pandas as pd

from flask import Response
from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField, FloatField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator, NumberRange

from limbless_db import models
from limbless_db.categories import GenomeRef

from .... import tools
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from .CompleteSASForm import CompleteSASForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


class PoolSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    pool_name = StringField("Library (-Pool) Label", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)], description="Unique label to identify the pool")  # type: ignore

    num_m_reads = FloatField("Number of Reads (million) required", validators=[DataRequired(), NumberRange(min=0, max=1000000)], description="Number of reads required from sequencing")  # type: ignore

    contact_person_name = StringField("Contact Person Name", validators=[DataRequired(), Length(max=models.Contact.name.type.length)], description="Who prepared the libraries?")  # type: ignore
    contact_person_email = StringField("Contact Person Email", validators=[DataRequired(), Length(max=models.Contact.email.type.length)], description="Who prepared the libraries?")  # type: ignore
    contact_person_phone = StringField("Contact Person Phone", validators=[OptionalValidator(), Length(max=models.Contact.phone.type.length)], description="Who prepared the libraries?")  # type: ignore


class PoolMappingForm(HTMXFlaskForm, TableDataForm):
    input_fields = FieldList(FormField(PoolSubForm), min_entries=1)

    _template_path = "workflows/library_annotation/sas-11.html"

    def __init__(self, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)

    def prepare(self):
        library_table = self.tables["library_table"]
        pools = library_table["pool"].unique().tolist()

        for i, raw_pool_label in enumerate(pools):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.raw_label.data = raw_pool_label

            if entry.pool_name.data is None:
                entry.pool_name.data = raw_pool_label
            if entry.contact_person_name.data is None:
                entry.contact_person_name.data = current_user.name
            if entry.contact_person_email.data is None:
                entry.contact_person_email.data = current_user.email

        library_table = tools.check_indices(library_table, "pool")
        library_table["genome_ref"] = library_table["genome_id"].map(GenomeRef.get)

        self._context["library_table"] = library_table
        self._context["pools"] = pools
        self._context["show_index_1"] = "index_1" in library_table.columns and library_table["index_1"].notna().any()
        self._context["show_index_2"] = "index_2" in library_table.columns and library_table["index_2"].notna().any()
        self._context["show_index_3"] = "index_3" in library_table.columns and library_table["index_3"].notna().any()
        self._context["show_index_4"] = "index_4" in library_table.columns and library_table["index_4"].notna().any()
        self._context["show_adapter"] = "adapter" in library_table.columns and library_table["adapter"].notna().any()

    def validate(self):
        validated = super().validate()
        if not validated:
            return False
        
        labels = []
        for i, entry in enumerate(self.input_fields):
            pool_label = entry.pool_name.data

            if pool_label in labels:
                entry.pool_name.errors = ("Pool label is not unique.",)
                validated = False
            labels.append(pool_label)

        return validated, self
    
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            self.prepare()
            return self.make_response(**context)
        
        library_table = self.tables["library_table"]
        library_table["pool"] = library_table["pool"].astype(str)
        library_table["pool"] = library_table["pool"].apply(tools.make_alpha_numeric)
        raw_pool_labels = library_table["pool"].unique().tolist()

        pool_data = {
            "name": [],
            "num_m_reads": [],
            "contact_person_name": [],
            "contact_person_email": [],
            "contact_person_phone": [],
        }

        for i, entry in enumerate(self.input_fields):
            pool_data["name"].append(entry.pool_name.data)
            pool_data["num_m_reads"].append(entry.num_m_reads.data)
            pool_data["contact_person_name"].append(entry.contact_person_name.data)
            pool_data["contact_person_email"].append(entry.contact_person_email.data)
            pool_data["contact_person_phone"].append(entry.contact_person_phone.data)

        for i, entry in enumerate(self.input_fields):
            pool_label = entry.pool_name.data
            library_table.loc[library_table["pool"] == raw_pool_labels[i], "pool"] = pool_label

        self.add_table("pool_table", pd.DataFrame(pool_data))
        self.update_table("library_table", library_table)
        
        complete_sas_form = CompleteSASForm(self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response(**context)