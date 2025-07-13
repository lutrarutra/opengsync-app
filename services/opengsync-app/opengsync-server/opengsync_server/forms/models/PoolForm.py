from typing import Optional, Literal

from flask import Response, url_for, flash
from wtforms import StringField, SelectField, FloatField, FormField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import PoolStatus, PoolType

from ... import logger, db  # noqa F401
from ..SearchBar import OptionalSearchBar
from ..HTMXFlaskForm import HTMXFlaskForm


class PoolForm(HTMXFlaskForm):
    _template_path = "forms/pool.html"
    _form_label = "pool_form"

    name = StringField("Pool Name", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)])
    pool_type = SelectField("Pool Type", choices=PoolType.as_selectable(), coerce=int)
    num_m_reads_requested = FloatField("Number of M Reads Requested", validators=[OptionalValidator()])
    status = SelectField("Status", choices=PoolStatus.as_selectable(), coerce=int)
    contact = FormField(OptionalSearchBar, "Select Existing Contact")
    contact_name = StringField("Contact Name", validators=[OptionalValidator(), Length(max=models.Contact.name.type.length)])
    contact_email = StringField("Contact Email", validators=[OptionalValidator(), Length(max=models.Contact.email.type.length)])
    contact_phone = StringField("Contact Phone", validators=[OptionalValidator(), Length(max=models.Contact.phone.type.length)])

    def __init__(self, form_type: Literal["edit", "create", "clone"], pool: models.Pool | None = None, formdata=None):
        super().__init__(formdata=formdata)
        self.pool = pool
        if form_type in ("edit", "clone") and pool is None:
            logger.error("Pool must be provided for edit or clone form type")
            raise ValueError("Pool must be provided for edit or clone form type")
        else:
            self._context["pool"] = pool
        self.form_type = form_type
        self._context["form_type"] = form_type

    def validate(self, user: models.User) -> bool:
        if not super().validate():
            return False
        
        if self.contact.selected.data is None and not self.contact_name.data:
            self.contact_name.errors = ("Select an existing contact or provide a name",)
            return False
        
        if self.contact.selected.data is None and not self.contact_email.data:
            self.contact_email.errors = ("Select an existing contact or provide a email",)
            return False
        
        pool_type = PoolType.get(self.pool_type.data)
        if self.form_type == "edit":
            if self.pool is None:
                raise Exception("Pool not passed as argument for edit form")
            if pool_type != self.pool.type:
                self.pool_type.errors = ("Pool type cannot be changed, please create a new pool",)
                return False
            for pool in self.pool.owner.pools:
                if pool.name == self.name.data and self.pool.id != pool.id:
                    self.name.errors = ("Owner of the pool already has a pool with the same name.",)
                    return False
        elif self.form_type == "create":
            for pool in user.pools:
                if pool.name == self.name.data:
                    self.name.errors = ("Owner of the pool already has a pool with the same name.",)
                    return False
        elif self.form_type == "clone":
            if self.pool is None:
                raise Exception("Pool not passed as argument for clone form")
            if pool_type != self.pool.type:
                self.pool_type.errors = ("Pool type cannot be changed, please create a new pool",)
                return False
            for pool in self.pool.owner.pools:
                if pool.name == self.name.data:
                    self.name.errors = ("Owner of the pool already has a pool with the same name.",)
                    return False
        return True

    def prepare(self):
        if self.pool is None:
            logger.error("Pool not passed as argument for edit form")
            raise ValueError("Pool not passed as argument for edit form")
        
        self.name.data = self.pool.name
        self.pool_type.data = self.pool.type.id
        self.status.data = self.pool.status_id
        self.num_m_reads_requested.data = self.pool.num_m_reads_requested
        if self.pool.contact is not None:
            self.contact_name.data = self.pool.contact.name
            self.contact_email.data = self.pool.contact.email
            self.contact_phone.data = self.pool.contact.phone

    def __edit_existing_pool(self) -> models.Pool:
        if self.pool is None:
            logger.error("Pool not passed as argument for edit form")
            raise ValueError("Pool not passed as argument for edit form")
        
        self.pool.name = self.name.data  # type: ignore
        self.pool.status = PoolStatus.get(self.status.data)
        self.pool.type = PoolType.get(self.pool_type.data)
        self.pool.num_m_reads_requested = self.num_m_reads_requested.data
        self.pool.contact.name = self.contact_name.data  # type: ignore
        self.pool.contact.email = self.contact_email.data  # type: ignore
        self.pool.contact.phone = self.contact_phone.data  # type: ignore

        self.pool = db.update_pool(self.pool)

        return self.pool

    def __create_new_pool(self, user: models.User) -> models.Pool:
        if (contact_id := self.contact.selected.data) is not None:
            if (contact := db.get_user(contact_id)) is None:
                logger.error(f"Contact {contact_id} not found")
                raise ValueError(f"Contact {contact_id} not found")
            
        pool_type = PoolType.get(self.pool_type.data)
            
        pool = db.create_pool(
            name=self.name.data,  # type: ignore
            status=PoolStatus.get(self.status.data),
            num_m_reads_requested=self.num_m_reads_requested.data,
            owner_id=user.id,
            pool_type=pool_type,
            contact_name=self.contact_name.data if contact is None else contact.name,  # type: ignore
            contact_email=self.contact_email.data if contact is None else contact.email,  # type: ignore
            contact_phone=self.contact_phone.data  # type: ignore
        )
        return pool
    
    def __clone_pool(self, user: models.User) -> models.Pool:
        if self.pool is None:
            logger.error("Pool not passed as argument for clone form")
            raise ValueError("Pool not passed as argument for clone form")
        
        pool = db.create_pool(
            name=self.name.data,  # type: ignore
            status=PoolStatus.get(self.status.data),
            num_m_reads_requested=self.num_m_reads_requested.data,
            owner_id=user.id,
            pool_type=self.pool.type,
            contact_email=self.pool.contact.email if self.pool.contact.email is not None else "unknown",
            contact_name=self.pool.contact.name,
            contact_phone=self.pool.contact.phone,
        )

        for library in self.pool.libraries:
            clone_library = db.clone_library(library.id, seq_request_id=library.seq_request_id, indexed=True)
            clone_library = db.pool_library(library_id=clone_library.id, pool_id=pool.id)
            
        return pool
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate(user):
            return self.make_response()
        
        if self.form_type == "edit":
            pool = self.__edit_existing_pool()
            flash(f"Edited pool {pool.name}", "success")
        elif self.form_type == "create":
            pool = self.__create_new_pool(user)
            flash(f"Created pool {pool.name}", "success")
        elif self.form_type == "clone":
            pool = self.__clone_pool(user)
            flash(f"Cloned pool {pool.name}", "success")
        
        return make_response(redirect=url_for("pools_page.pool_page", pool_id=pool.id))
        
