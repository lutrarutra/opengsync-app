import string
from typing import Optional, Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import FeatureType
from ... import logger, db  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class FeatureKitForm(HTMXFlaskForm):
    _template_path = "forms/feature_kit.html"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=models.IndexKit.name.type.length)])
    identifier = StringField("Identifier", validators=[DataRequired(), Length(min=3, max=models.IndexKit.identifier.type.length)])
    feature_type_id = SelectField("Feature Type", choices=FeatureType.as_selectable(), validators=[OptionalValidator()], coerce=int)

    def __init__(
        self, form_type: Literal["create", "edit"],
        formdata: Optional[dict] = None,
        feature_kit: Optional[models.FeatureKit] = None
    ):
        super().__init__(formdata=formdata)
        self.form_type = form_type
        self.feature_kit = feature_kit
        if feature_kit is not None and formdata is None:
            self.__fill_form(feature_kit)
        if self.feature_kit is not None:
            self._context["feature_kit"] = feature_kit

    def __fill_form(self, feature_kit: models.FeatureKit):
        self.name.data = feature_kit.name
        self.identifier.data = feature_kit.identifier
        self.feature_type_id.data = feature_kit.type_id

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
                self.identifier.errors = ("Index kit with this identifier already exists.",)
                return False
            
            if (_kit := db.kits.get(name=self.name.data)) is not None:
                self.name.errors = ("Index kit with this name already exists.",)
                return False
        elif self.form_type == "edit":
            if self.feature_kit is None:
                logger.error("Index kit is not set.")
                raise ValueError("Index kit is not set.")
            
            if (_kit := db.kits.get(identifier=self.identifier.data)) is not None:
                if _kit.id != self.feature_kit.id:
                    self.identifier.errors = ("Index kit with this identifier already exists.",)
                    return False
            
            if (_kit := db.kits.get(name=self.name.data)) is not None:
                if _kit.id != self.feature_kit.id:
                    self.name.errors = ("Index kit with this name already exists.",)
                    return False
            if self.feature_kit.type != FeatureType.get(self.feature_type_id.data):
                self.feature_type_id.errors = ("Feature type cannot be changed.",)
                return False
        else:
            logger.error(f"Invalid form type '{self.form_type}'.")
            raise ValueError(f"Invalid form type '{self.form_type}'.")

        return True
    
    def __edit_feature_kit(self) -> Response:
        if self.feature_kit is None:
            logger.error("Index kit is not set.")
            raise ValueError("Index kit is not set.")
        
        self.feature_kit.name = self.name.data  # type: ignore
        self.feature_kit.identifier = self.identifier.data  # type: ignore
        self.feature_kit.type_id = self.feature_type_id.data  # type: ignore
        db.feature_kits.update(self.feature_kit)
        flash("Index kit updated successfully.", "success")
        return make_response(redirect=url_for("kits_page.feature_kit", feature_kit_id=self.feature_kit.id))
        
    def __create_feature_kit(self) -> Response:
        feature_kit = db.feature_kits.create(
            name=self.name.data,  # type: ignore
            identifier=self.identifier.data,  # type: ignore
            type=FeatureType.get(self.feature_type_id.data),
        )
        flash("Index kit created successfully.", "success")
        return make_response(redirect=url_for("kits_page.feature_kit", feature_kit_id=feature_kit.id))
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        if self.form_type == "edit":
            return self.__edit_feature_kit()

        elif self.form_type == "create":
            return self.__create_feature_kit()

        logger.error(f"Invalid form type '{self.form_type}'.")
        raise ValueError(f"Invalid form type '{self.form_type}'.")