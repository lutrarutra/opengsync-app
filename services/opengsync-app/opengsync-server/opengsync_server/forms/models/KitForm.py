import string
from typing import Optional, Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField
from wtforms.validators import DataRequired, Length

from opengsync_db import models
from opengsync_db.categories import KitType
from ... import logger, db  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class KitForm(HTMXFlaskForm):
    _template_path = "forms/kit.html"
    _form_label = "kit_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=models.Kit.name.type.length)])
    identifier = StringField("Identifier", validators=[DataRequired(), Length(min=3, max=models.Kit.identifier.type.length)])

    def __init__(
        self, form_type: Literal["create", "edit"],
        formdata: Optional[dict] = None,
        kit: Optional[models.Kit] = None
    ):
        super().__init__(formdata=formdata)
        self.form_type = form_type
        self.kit = kit
        if kit is not None and formdata is None:
            self.__fill_form(kit)
        if self.kit is not None:
            self._context["kit"] = kit

    def __fill_form(self, kit: models.Kit):
        self.name.data = kit.name
        self.identifier.data = kit.identifier

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.identifier.data is None:
            self.identifier.errors = ("Identifier is required.",)
            return False
        
        if self.name.data is None:
            self.name.errors = ("Name is required.",)
            return False
        
        for whitespace in string.whitespace:
            if whitespace in self.identifier.data:
                self.identifier.errors = ("Identifier cannot contain whitespace.",)
                return False
        
        if self.form_type == "create":
            if (_kit := db.kits.get(identifier=self.identifier.data)) is not None:
                self.identifier.errors = ("Kit with this identifier already exists.",)
                return False
            
            if (_kit := db.kits.get(name=self.name.data)) is not None:
                self.name.errors = ("Kit with this name already exists.",)
                return False
        elif self.form_type == "edit":
            if self.kit is None:
                logger.error("Kit is not set.")
                raise ValueError("Kit is not set.")
            
            if (_kit := db.kits.get(identifier=self.identifier.data)) is not None:
                if _kit.id != self.kit.id:
                    self.identifier.errors = ("Kit with this identifier already exists.",)
                    return False
            
            if (_kit := db.kits.get(name=self.name.data)) is not None:
                if _kit.id != self.kit.id:
                    self.name.errors = ("Kit with this name already exists.",)
                    return False
        else:
            logger.error(f"Invalid form type '{self.form_type}'.")
            raise ValueError(f"Invalid form type '{self.form_type}'.")

        return True
    
    def __edit_kit(self) -> Response:
        if self.kit is None:
            logger.error("Kit is not set.")
            raise ValueError("Kit is not set.")
        
        self.kit.name = self.name.data  # type: ignore
        self.kit.identifier = self.identifier.data  # type: ignore
        self.kit = db.kits.update(self.kit)
        flash("Kit updated successfully.", "success")
        return make_response(redirect=url_for("kits_page.kit", kit_id=self.kit.id))
        
    def __create_kit(self) -> Response:
        kit = db.kits.create(
            name=self.name.data,  # type: ignore
            identifier=self.identifier.data,  # type: ignore
            kit_type=KitType.LIBRARY_KIT,
        )
        flash("Kit created successfully.", "success")
        return make_response(redirect=url_for("kits_page.kit", kit_id=kit.id))
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        if self.form_type == "edit":
            return self.__edit_kit()

        elif self.form_type == "create":
            return self.__create_kit()

        logger.error(f"Invalid form type '{self.form_type}'.")
        raise ValueError(f"Invalid form type '{self.form_type}'.")