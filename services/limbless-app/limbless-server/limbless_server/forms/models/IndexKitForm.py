import string
from typing import Optional, Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import IndexType
from ... import logger, db  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class IndexKitForm(HTMXFlaskForm):
    _template_path = "forms/index_kit.html"
    _form_label = "index_kit_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=models.IndexKit.name.type.length)])
    identifier = StringField("Identifier", validators=[DataRequired(), Length(min=3, max=models.IndexKit.identifier.type.length)])
    index_type_id = SelectField("Index Type", choices=IndexType.as_selectable(), validators=[OptionalValidator()], coerce=int)

    def __init__(
        self, form_type: Literal["create", "edit"],
        formdata: Optional[dict] = None,
        index_kit: Optional[models.IndexKit] = None
    ):
        super().__init__(formdata=formdata)
        self.form_type = form_type
        self.index_kit = index_kit
        if index_kit is not None and formdata is None:
            self.__fill_form(index_kit)
        if self.index_kit is not None:
            self._context["index_kit"] = index_kit

    def __fill_form(self, index_kit: models.IndexKit):
        self.name.data = index_kit.name
        self.identifier.data = index_kit.identifier
        self.index_type_id.data = index_kit.type_id

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
            if (_kit := db.get_kit(identifier=self.identifier.data)) is not None:
                self.identifier.errors = ("Index kit with this identifier already exists.",)
                return False
            
            if (_kit := db.get_kit(name=self.name.data)) is not None:
                self.name.errors = ("Index kit with this name already exists.",)
                return False
        elif self.form_type == "edit":
            if self.index_kit is None:
                logger.error("Index kit is not set.")
                raise ValueError("Index kit is not set.")
            
            if (_kit := db.get_kit(identifier=self.identifier.data)) is not None:
                if _kit.id != self.index_kit.id:
                    self.identifier.errors = ("Index kit with this identifier already exists.",)
                    return False
            
            if (_kit := db.get_kit(name=self.name.data)) is not None:
                if _kit.id != self.index_kit.id:
                    self.name.errors = ("Index kit with this name already exists.",)
                    return False
        else:
            logger.error(f"Invalid form type '{self.form_type}'.")
            raise ValueError(f"Invalid form type '{self.form_type}'.")

        return True
    
    def __edit_index_kit(self) -> Response:
        if self.index_kit is None:
            logger.error("Index kit is not set.")
            raise ValueError("Index kit is not set.")
        
        logger.debug(self.identifier.data)
        
        self.index_kit.name = self.name.data  # type: ignore
        self.index_kit.identifier = self.identifier.data  # type: ignore
        self.index_kit.type_id = self.index_type_id.data  # type: ignore
        self.index_kit = db.update_index_kit(self.index_kit)
        flash("Index kit updated successfully.", "success")
        return make_response(redirect=url_for("kits_page.index_kit_page", index_kit_id=self.index_kit.id))
        
    def __create_index_kit(self) -> Response:
        index_kit = db.create_index_kit(
            name=self.name.data,  # type: ignore
            identifier=self.identifier.data,  # type: ignore
            type=IndexType.get(self.index_type_id.data),
            supported_protocols=[]
        )
        flash("Index kit created successfully.", "success")
        return make_response(redirect=url_for("kits_page.index_kit_page", index_kit_id=index_kit.id))
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        if self.form_type == "edit":
            return self.__edit_index_kit()

        elif self.form_type == "create":
            return self.__create_index_kit()

        logger.error(f"Invalid form type '{self.form_type}'.")
        raise ValueError(f"Invalid form type '{self.form_type}'.")