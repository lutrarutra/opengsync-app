from typing import Optional, TYPE_CHECKING
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from limbless_db import models
from ... import db
from ..TableDataForm import TableDataForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

from ..HTMXFlaskForm import HTMXFlaskForm
from .BarcodeCheckForm import BarcodeCheckForm


class PoolSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    pool_name = StringField("Library (-Pool) Label", validators=[DataRequired(), Length(min=4, max=64)], description="Unique label to identify the pool")
    contact_person_name = StringField("Contact Person Name", validators=[DataRequired(), Length(max=128)], description="Who prepared the libraries?")
    contact_person_email = StringField("Contact Person Email", validators=[DataRequired(), Length(max=128)], description="Who prepared the libraries?")
    contact_person_phone = StringField("Contact Person Phone", validators=[OptionalValidator(), Length(max=16)], description="Who prepared the libraries?")


class PoolMappingForm(HTMXFlaskForm, TableDataForm):
    input_fields = FieldList(FormField(PoolSubForm), min_entries=1)

    _template_path = "components/popups/pooling/pooling-3.html"
    _form_label = "pool_mapping_form"

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()

        df = data["pooling_table"]

        df["pool"] = df["pool"].apply(lambda x: str(x) if x and not pd.isna(x) and not pd.isnull(x) else "__NONE__")

        pool_libraries = []
        raw_pool_labels = df["pool"].unique().tolist()

        for i, raw_pool_label in enumerate(raw_pool_labels):
            _df = df[df["pool"] == raw_pool_label]

            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            raw_pool_label = raw_pool_label if raw_pool_label != "__NONE__" else f"Pool {i+1}"
            entry = self.input_fields[i]
            entry.raw_label.data = raw_pool_label

            if entry.pool_name.data is None:
                entry.pool_name.data = raw_pool_label if raw_pool_label != "__NONE__" else ""
            if entry.contact_person_name.data is None:
                entry.contact_person_name.data = current_user.name
            if entry.contact_person_email.data is None:
                entry.contact_person_email.data = current_user.email

            libraries = []
            for _, row in _df.iterrows():
                library_id = row["id"]
                library = db.get_library(library_id)
                libraries.append(library)

            pool_libraries.append(libraries)

        data["pooling_table"] = df
        self.update_data(data)

        return {
            "pool_libraries": pool_libraries,
        }

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

    def __parse(self) -> dict[str, pd.DataFrame]:
        data = self.get_data()
        df = data["pooling_table"]

        df["contact_person_name"] = None
        df["contact_person_email"] = None
        df["contact_person_phone"] = None

        df["pool"] = df["pool"].astype(str)
        raw_pool_labels = df["pool"].unique().tolist()
        for i, entry in enumerate(self.input_fields):
            df.loc[df["pool"] == raw_pool_labels[i], "contact_person_name"] = entry.contact_person_name.data
            df.loc[df["pool"] == raw_pool_labels[i], "contact_person_email"] = entry.contact_person_email.data
            df.loc[df["pool"] == raw_pool_labels[i], "contact_person_phone"] = entry.contact_person_phone.data

        for i, entry in enumerate(self.input_fields):
            pool_label = entry.pool_name.data
            df.loc[df["pool"] == raw_pool_labels[i], "pool"] = pool_label

        data["pooling_table"] = df
        self.update_data(data)

        return data
    
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            context = context | self.prepare()
            return self.make_response(**context)
        
        data = self.__parse()

        barcode_check_form = BarcodeCheckForm(uuid=self.uuid)
        context = barcode_check_form.prepare(data) | context
        return barcode_check_form.make_response(**context)