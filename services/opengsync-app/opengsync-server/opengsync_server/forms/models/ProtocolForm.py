from typing import Optional, Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import ServiceType
from ... import logger, db  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class ProtocolForm(HTMXFlaskForm):
    _template_path = "forms/protocol.html"
    _form_label = "protocol_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=models.Protocol.name.type.length)])
    service_type = SelectField("Assay Type", choices=ServiceType.as_selectable(), coerce=int, validators=[DataRequired()])
    read_structure = StringField("Read Structure", validators=[OptionalValidator(), Length(max=models.Protocol.read_structure.type.length)], description="Read structure defining the layout of reads, UMIs and indexes.")

    def __init__(
        self, form_type: Literal["create", "edit"],
        formdata: Optional[dict] = None,
        protocol: Optional[models.Protocol] = None
    ):
        super().__init__(formdata=formdata)
        self.form_type = form_type
        self.protocol = protocol
        if protocol is not None and not formdata:
            self.__fill_form(protocol)
        if self.protocol is not None:
            self._context["protocol"] = protocol

        self._context["form_type"] = form_type

    def __fill_form(self, protocol: models.Protocol):
        self.name.data = protocol.name
        self.service_type.data = protocol.service_type.id
        self.read_structure.data = protocol.read_structure

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.name.data is None:
            self.name.errors = ("Name is required.",)
            return False
        
        if self.form_type == "create":            
            if (_protocol := db.protocols.get_by_name(name=self.name.data)) is not None:
                self.name.errors = ("protocol with this name already exists.",)
                return False
        elif self.form_type == "edit":
            if self.protocol is None:
                logger.error("protocol is not set.")
                raise ValueError("protocol is not set.")
            
            if (_protocol := db.protocols.get_by_name(name=self.name.data)) is not None:
                if _protocol.id != self.protocol.id:
                    self.name.errors = ("protocol with this name already exists.",)
                    return False
        else:
            logger.error(f"Invalid form type '{self.form_type}'.")
            raise ValueError(f"Invalid form type '{self.form_type}'.")

        return True
    
    def __edit_protocol(self) -> Response:
        if self.protocol is None:
            logger.error("protocol is not set.")
            raise ValueError("protocol is not set.")
        
        self.protocol.name = self.name.data.strip()  # type: ignore
        self.protocol.service_type = ServiceType.get(self.service_type.data)
        self.protocol.read_structure = self.read_structure.data.strip() if self.read_structure.data else None
        db.protocols.update(self.protocol)
        flash("protocol updated successfully.", "success")
        return make_response(redirect=url_for("protocols_page.protocol", protocol_id=self.protocol.id))
        
    def __create_protocol(self) -> Response:
        protocol = db.protocols.create(
            name=self.name.data.strip(),  # type: ignore
            service_type=ServiceType.get(self.service_type.data),
            read_structure=self.read_structure.data.strip() if self.read_structure.data else None,
        )
        flash("protocol created successfully.", "success")
        return make_response(redirect=url_for("protocols_page.protocol", protocol_id=protocol.id))
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        if self.form_type == "edit":
            return self.__edit_protocol()

        elif self.form_type == "create":
            return self.__create_protocol()

        logger.error(f"Invalid form type '{self.form_type}'.")
        raise ValueError(f"Invalid form type '{self.form_type}'.")