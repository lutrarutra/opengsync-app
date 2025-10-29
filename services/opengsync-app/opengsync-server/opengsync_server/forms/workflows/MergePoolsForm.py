import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField, FormField, SelectField, FloatField
from wtforms.validators import Optional as OptionalValidator, Length, DataRequired

from opengsync_db import models, exceptions
from opengsync_db.categories import PoolStatus, PoolType

from ...core import exceptions as serv_exceptions
from ... import db, logger, tools  # noqa F401
from ..MultiStepForm import MultiStepForm
from ..SearchBar import OptionalSearchBar


class MergePoolsForm(MultiStepForm):
    _template_path = "workflows/merge_pools.html"
    _workflow_name = "merge_pools"
    _step_name = "merge_pools"

    name = StringField("Pool Name", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)])
    pool_type = SelectField("Pool Type", choices=PoolType.as_selectable(), coerce=int)
    num_m_reads_requested = FloatField("Number of M Reads Requested", validators=[OptionalValidator()])
    status = SelectField("Status", choices=PoolStatus.as_selectable(), coerce=int)
    contact = FormField(OptionalSearchBar, "Select Existing Contact")
    contact_name = StringField("Contact Name", validators=[OptionalValidator(), Length(max=models.Contact.name.type.length)])
    contact_email = StringField("Contact Email", validators=[OptionalValidator(), Length(max=models.Contact.email.type.length)])
    contact_phone = StringField("Contact Phone", validators=[OptionalValidator(), Length(max=models.Contact.phone.type.length)])

    def __init__(self, uuid: str, formdata=None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, step_name=MergePoolsForm._step_name,
            workflow=MergePoolsForm._workflow_name, step_args={}
        )
        self.pool_table = self.tables["pool_table"]
        self.barcode_table = self.tables["barcode_table"]
        self.pool_table["num_m_reads_requested"] = 0
        self.library_table = self.tables["library_table"]
        self.post_url = url_for("merge_pools_workflow.merge", uuid=uuid)
        logger.debug(self.barcode_table)
        self._context["barcode_table"] = tools.check_indices(self.barcode_table)
        self._context["library_table"] = self.library_table

    def prepare(self):
        self.num_m_reads_requested.data = self.pool_table["num_m_reads_requested"].sum()

    def validate(self, user: models.User) -> bool:
        if not super().validate():
            return False

        for pool in user.pools:
            if pool.name == self.name.data and pool.name not in self.pool_table["name"].tolist():
                self.name.errors = ("Owner of the pool already has a pool with the same name.",)
        
        if not self.contact.selected.data:
            if not self.contact_name.data:
                self.contact_name.errors = ("Contact is required",)
            
            if not self.contact_email.data:
                self.contact_email.errors = ("Contact is required",)
        
        return len(self.errors) == 0

    def process_request(self, user: models.User) -> Response:
        if not self.validate(user):
            return self.make_response()
        
        if (contact_id := self.contact.selected.data) is not None:
            if (contact := db.users.get(contact_id)) is None:
                logger.error(f"Contact {contact_id} not found")
                raise exceptions.ElementDoesNotExist(f"Contact {contact_id} not found")
        else:
            contact = None
            
        pool_type = PoolType.get(self.pool_type.data)
            
        pool = db.pools.create(
            name=self.name.data,  # type: ignore
            status=PoolStatus.get(self.status.data),
            num_m_reads_requested=self.num_m_reads_requested.data,
            owner_id=user.id,
            pool_type=pool_type,
            contact_name=self.contact_name.data if contact is None else contact.name,  # type: ignore
            contact_email=self.contact_email.data if contact is None else contact.email,  # type: ignore
            contact_phone=self.contact_phone.data  # type: ignore
        )

        pool = db.pools.merge(
            merged_pool_id=pool.id,
            pool_ids=[int(x) for x in self.pool_table["id"].tolist()],
        )

        if len(pool.libraries) != len(self.library_table):
            logger.error(f"{self.uuid}: Mismatch in number of libraries after merging pools. Expected {len(self.pool_table)}, got {len(pool.libraries)}")
            raise serv_exceptions.InternalServerErrorException("Mismatch in number of libraries after merging pools.")
    
        flash("Pools Merged!")
        logger.info(f"{self.uuid}: Pools merged successfully. New pool ID: {pool.id}")
        return make_response(redirect=url_for("pools_page.pool", pool_id=pool.id))