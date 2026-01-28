from typing import Optional

import pandas as pd

from flask import Response
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FormField, FieldList
from wtforms.validators import Length, Optional as OptionalValidator, DataRequired

from opengsync_db import models

from .... import logger, db
from ....tools import utils
from ...MultiStepForm import MultiStepForm
from .BarcodeInputForm import BarcodeInputForm, TENXATACBarcodeInputForm


class PoolMappingSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    new_pool_name = StringField("Pool Name", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)])
    num_m_reads_requested = FloatField("Number of M Reads Requested", validators=[OptionalValidator()])


class PoolMappingForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-pool_mapping.html"
    _workflow_name = "library_annotation"
    _step_name = "pool_mapping"

    pool_forms = FieldList(FormField(PoolMappingSubForm), label="Pool Mapping")
    contact_name = StringField("Contact Name", validators=[DataRequired(), Length(max=models.Contact.name.type.length)])
    contact_email = StringField("Contact Email", validators=[DataRequired(), Length(max=models.Contact.email.type.length)])
    contact_phone = StringField("Contact Phone", validators=[DataRequired(), Length(max=models.Contact.phone.type.length)])

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=PoolMappingForm._workflow_name,
            step_name=PoolMappingForm._step_name,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.library_table = self.tables["library_table"]
        self.raw_pool_labels = self.library_table["pool"].unique().tolist()

    def prepare(self):
        if self.seq_request.contact_person:
            if not self.contact_name.data:
                self.contact_name.data = self.seq_request.contact_person.name
            if not self.contact_email.data:
                self.contact_email.data = self.seq_request.contact_person.email
            if not self.contact_phone.data:
                self.contact_phone.data = self.seq_request.contact_person.phone

        for i, pool in enumerate(self.raw_pool_labels):
            if i > len(self.pool_forms) - 1:
                self.pool_forms.append_entry()

            sub_form: PoolMappingSubForm = self.pool_forms[i]  # type: ignore
            sub_form.raw_label.data = str(pool)

            if not sub_form.new_pool_name.data:
                sub_form.new_pool_name.data = str(pool)
        
    def fill_previous_form(self):
        pool_table = self.tables["pool_table"]

        self.contact_name.data = self.metadata.get("pool_contact_name")
        self.contact_email.data = self.metadata.get("pool_contact_email")
        self.contact_phone.data = self.metadata.get("pool_contact_phone")

        for i, (idx, row) in enumerate(pool_table.iterrows()):
            if i > len(self.pool_forms) - 1:
                self.pool_forms.append_entry()

            sub_form: PoolMappingSubForm = self.pool_forms[i]  # type: ignore
            sub_form.raw_label.data = row["pool_label"]
            sub_form.new_pool_name.data = row["pool_name"]
            sub_form.num_m_reads_requested.data = row["num_m_reads_requested"]

    def validate(self, user: models.User) -> bool:
        if not super().validate():
            return False

        pool_table_data = {
            "pool_name": [],
            "pool_label": [],
            "pool_id": [],
            "num_m_reads_requested": [],
        }

        def add_pool(name: str, label: str, pool_id: Optional[int], num_m_reads_requested: Optional[float]):
            pool_table_data["pool_name"].append(name)
            pool_table_data["pool_id"].append(pool_id)
            pool_table_data["pool_label"].append(label)
            pool_table_data["num_m_reads_requested"].append(num_m_reads_requested)

        sub_form: PoolMappingSubForm
        for sub_form in self.pool_forms:  # type: ignore
            # if sub_form.new_pool_name.data and sub_form.existing_pool.selected.data:
            #     sub_form.existing_pool.selected.errors = ["Define new pool or select an existing pool, not both."]
            #     sub_form.new_pool_name.errors = ["Define new pool or select an existing pool, not both."]
            #     return False
            
            # if not sub_form.new_pool_name.data and not sub_form.existing_pool.selected.data:
            #     sub_form.new_pool_name.errors = ["Define new pool or select an existing pool."]
            #     sub_form.existing_pool.selected.errors = ["Define new pool or select an existing pool."]
            #     return False
            
            if sub_form.new_pool_name.data:
                sub_form.new_pool_name.data = sub_form.new_pool_name.data.strip()
                if sub_form.new_pool_name.data in [pool.name for pool in user.pools]:
                    sub_form.new_pool_name.errors = ["You already have a pool with this name."]
                    return False

                if (error := utils.check_string(sub_form.new_pool_name.data)) is not None:
                    sub_form.new_pool_name.errors = [error]
                    return False

                add_pool(
                    name=sub_form.new_pool_name.data,
                    label=sub_form.raw_label.data,  # type: ignore
                    pool_id=None,
                    num_m_reads_requested=sub_form.num_m_reads_requested.data,
                )
            # elif sub_form.existing_pool.selected.data:
            #     if (pool := db.pools.get_pool(int(sub_form.existing_pool.seleted.data))) is None:
            #         logger.error(f"Pool with ID {sub_form.existing_pool.seleted.data} not found.")
            #         raise Exception(f"Pool with ID {sub_form.existing_pool.seleted.data} not found.")
            #     add_pool(
            #         name=pool.name,
            #         label=sub_form.raw_label.data,  # type: ignore
            #         pool_id=pool.id,
            #         num_m_reads_requested=sub_form.num_m_reads_requested.data,
            #     )

        self.pool_table = pd.DataFrame(pool_table_data)
        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate(user=user):
            return self.make_response()

        self.metadata["pool_contact_name"] = self.contact_name.data
        self.metadata["pool_contact_email"] = self.contact_email.data
        self.metadata["pool_contact_phone"] = self.contact_phone.data
        self.tables["pool_table"] = self.pool_table
        self.step()

        if BarcodeInputForm.is_applicable(self):
            next_form = BarcodeInputForm(
                seq_request=self.seq_request,
                uuid=self.uuid,
            )
        elif TENXATACBarcodeInputForm.is_applicable(self):
            next_form = TENXATACBarcodeInputForm(
                seq_request=self.seq_request,
                uuid=self.uuid,
            )
        else:
            raise Exception("No applicable barcode input form found.")
        return next_form.make_response()
