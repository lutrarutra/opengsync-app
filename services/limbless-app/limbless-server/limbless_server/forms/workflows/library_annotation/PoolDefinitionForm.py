from typing import Optional, TYPE_CHECKING

from flask import Response
from wtforms import StringField, FloatField, FormField
from wtforms.validators import Length, Optional as OptionalValidator

from limbless_db import models

from .... import logger, db  # noqa F401
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from .IndexKitSelectForm import IndexKitSelectForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


class PoolDefinitionForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-1.2.html"
    _form_label = "pool_form"

    name = StringField("Pool Name", validators=[OptionalValidator(), Length(min=4, max=models.Pool.name.type.length)])
    num_m_reads_requested = FloatField("Number of M Reads Requested", validators=[OptionalValidator()])
    contact_name = StringField("Contact Name", validators=[OptionalValidator(), Length(max=models.Contact.name.type.length)])
    contact_email = StringField("Contact Email", validators=[OptionalValidator(), Length(max=models.Contact.email.type.length)])
    contact_phone = StringField("Contact Phone", validators=[OptionalValidator(), Length(max=models.Contact.phone.type.length)])

    existing_pool = FormField(OptionalSearchBar, label="Select Existing Pool")

    def __init__(self, seq_request: models.SeqRequest, formdata: dict = {}, uuid: Optional[str] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = formdata.get("file_uuid")
        TableDataForm.__init__(self, uuid=uuid, dirname="library_annotation")
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self, user: models.User) -> bool:
        if not super().validate():
            return False
        
        if self.name.data and self.existing_pool.selected.data:
            self.existing_pool.selected.errors = ["Define new pool or select an existing pool, not both."]
            self.name.errors = ["Define new pool or select an existing pool, not both."]
            return False
        
        if not self.name.data and not self.existing_pool.selected.data:
            self.name.errors = ["Define new pool or select an existing pool."]
            self.existing_pool.selected.errors = ["Define new pool or select an existing pool."]
            return False
        
        if self.name.data:
            if not self.contact_name.data:
                self.contact_name.errors = ["This field is required."]
                return False
            if not self.contact_email.data:
                self.contact_email.errors = ["This field is required."]
                return False
            if not self.contact_phone.data:
                self.contact_phone.errors = ["This field is required."]
                return False
            
            self.name.data = self.name.data.strip()
            if self.name.data in [pool.name for pool in user.pools]:
                self.name.errors = ["You already have a pool with this name."]
                return False

        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate(user=user):
            return self.make_response()
        
        index_kit_select_form = IndexKitSelectForm(seq_request=self.seq_request, uuid=self.uuid)
        index_kit_select_form.metadata["pool_name"] = self.name.data
        index_kit_select_form.metadata["pool_num_m_reads_requested"] = self.num_m_reads_requested.data
        index_kit_select_form.metadata["pool_contact_name"] = self.contact_name.data
        index_kit_select_form.metadata["pool_contact_email"] = self.contact_email.data
        index_kit_select_form.metadata["pool_contact_phone"] = self.contact_phone.data
        index_kit_select_form.metadata["existing_pool_id"] = self.existing_pool.selected.data
        index_kit_select_form.update_data()
        return index_kit_select_form.make_response()
