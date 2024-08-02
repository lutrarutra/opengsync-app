from typing import Optional, Literal

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired

from limbless_db import models
from limbless_db.categories import LabProtocol

from ... import db, logger  # noqa F401
from ..HTMXFlaskForm import HTMXFlaskForm


class LabPrepForm(HTMXFlaskForm):
    _template_path = "forms/lab_prep.html"
    _form_label = "lab_prep_form"

    protocol = SelectField("Protocol", choices=LabProtocol.as_selectable(), coerce=int)
    name = StringField("Name", validators=[DataRequired()])

    def __init__(self, form_type: Literal["create", "edit"], lab_prep: Optional[models.LabPrep] = None, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.form_type = form_type
        self.lab_prep = lab_prep
        self._context["identifiers"] = dict([(pool_type.id, pool_type.identifier) for pool_type in LabProtocol.as_list()])

        if self.form_type == "edit":
            if self.lab_prep is None:
                logger.error("lab_prep must be provided if form_type is 'edit'.")
                raise ValueError("lab_prep must be provided if form_type is 'edit'.")
            self.__fill_form(self.lab_prep)

    def __fill_form(self, lab_prep: models.LabPrep):
        self.protocol.data = lab_prep.protocol_id
        self.name.data = lab_prep.name

    def validate(self) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        try:
            protocol = LabProtocol.get(self.protocol.data)
        except ValueError:
            self.protocol.errors = ("Invalid protocol",)
            return False
        
        if protocol.identifier:
            self.name.data = db.get_next_protocol_identifier(protocol)

        return validated
    
    def __edit_lab_prep(self) -> models.LabPrep:
        if self.lab_prep is None:
            logger.error("lab_prep must be provided if form_type is 'edit'.")
            raise ValueError("lab_prep must be provided if form_type is 'edit'.")
        
        self.lab_prep.name = self.name.data  # type: ignore
        self.lab_prep.protocol_id = LabProtocol.get(self.protocol.data).id

        flash("Changes saved!", "success")
        return db.update_lab_prep(self.lab_prep)

    def __create_lab_prep(self, user: models.User) -> models.LabPrep:
        lab_prep = db.create_lab_prep(
            name=self.name.data,  # type: ignore
            protocol=LabProtocol.get(self.protocol.data),
            creator_id=user.id
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
        
        return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=lab_prep.id))
        