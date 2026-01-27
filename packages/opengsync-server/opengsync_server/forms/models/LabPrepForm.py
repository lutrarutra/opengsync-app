from typing import Optional, Literal

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField, SelectField

from opengsync_db import models
from opengsync_db.categories import LabChecklistType, ServiceType

from ... import db, logger  # noqa F401
from ..HTMXFlaskForm import HTMXFlaskForm


class LabPrepForm(HTMXFlaskForm):
    _template_path = "forms/lab_prep.html"
    _form_label = "lab_prep_form"

    checklist_type = SelectField("Checklist", choices=LabChecklistType.as_selectable(), coerce=int)
    service_type = SelectField("Service", choices=ServiceType.as_selectable(), coerce=int)
    name = StringField("Name")

    def __init__(self, form_type: Literal["create", "edit"], lab_prep: Optional[models.LabPrep] = None, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.form_type = form_type
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep
        self._context["identifiers"] = dict([(pool_type.id, pool_type.identifier) for pool_type in LabChecklistType.as_list()])

        if self.form_type == "edit" and self.lab_prep is None:
            logger.error("lab_prep must be provided if form_type is 'edit'.")
            raise ValueError("lab_prep must be provided if form_type is 'edit'.")
    
    def prepare(self):
        if self.lab_prep is not None:
            self.checklist_type.data = self.lab_prep.checklist_type_id
            self.name.data = self.lab_prep.name
            self.service_type.data = self.lab_prep.service_type_id

    def validate(self) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        try:
            protocol = LabChecklistType.get(self.checklist_type.data)
        except ValueError:
            self.checklist_type.errors = ("Invalid protocol",)
            return False
        
        try:
            ServiceType.get(self.service_type.data)
        except ValueError:
            self.service_type.errors = ("Invalid assay type",)
            return False
        
        if self.form_type == "edit":
            if self.lab_prep is None:
                logger.error("lab_prep must be provided if form_type is 'edit'.")
                raise ValueError("lab_prep must be provided if form_type is 'edit'.")
            
            if not self.name.data:
                self.name.errors = ("Name is required",)
                validated = False
            if protocol != self.lab_prep.checklist_type:
                self.checklist_type.errors = ("Cannot change checklist type",)
                validated = False

        return validated
    
    def __edit_lab_prep(self) -> models.LabPrep:
        if self.lab_prep is None:
            logger.error("lab_prep must be provided if form_type is 'edit'.")
            raise ValueError("lab_prep must be provided if form_type is 'edit'.")
        
        self.lab_prep.name = self.name.data  # type: ignore
        self.lab_prep.service_type = ServiceType.get(self.service_type.data)

        flash("Changes saved!", "success")
        db.lab_preps.update(self.lab_prep)
        return self.lab_prep

    def __create_lab_prep(self, user: models.User) -> models.LabPrep:
        lab_prep = db.lab_preps.create(
            name=self.name.data,
            checklist_type=LabChecklistType.get(self.checklist_type.data),
            creator_id=user.id,
            service_type=ServiceType.get(self.service_type.data)
        )
        flash("Prep created!", "success")
        return lab_prep

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.form_type == "edit":
            lab_prep = self.__edit_lab_prep()
        else:
            lab_prep = self.__create_lab_prep(user=user)
        
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=lab_prep.id))
        