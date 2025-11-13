from typing import Optional

import pandas as pd
import json

from flask import url_for, flash
from flask_htmx import make_response
from wtforms import StringField

from opengsync_db import models

from .. import db, logger
from .HTMXFlaskForm import HTMXFlaskForm

class AddKitsToProtocolForm(HTMXFlaskForm):
    _template_path = "forms/select-protocol-kits.html"
    _step_name = "select_kits"

    selected_kit_ids = StringField()

    def __init__(
        self,
        protocol: models.Protocol,
        selected_kits: list[models.Kit] = [],
        formdata: dict | None = None,
    ):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.protocol = protocol
        self._context["selected_kit_ids"] = [kit.id for kit in selected_kits]
        self._context["selected_kits"] = selected_kits
        self._context["workflow"] = "add_kits_to_protocol"
        self._context["protocol"] = protocol
        self._context["post_url"] = url_for("protocols_htmx.add_kits", protocol_id=protocol.id)


    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.selected_kit_ids.data:
            self.selected_kit_ids.errors = ("No kits selected.",)
            return False
        
        kit_ids = json.loads(self.selected_kit_ids.data)
        if not kit_ids:
            self.selected_kit_ids.errors = ("No kits selected.",)
            return False

        self.kit_ids = []
        try:
            for sample_id in kit_ids:
                self.kit_ids.append(int(sample_id))
        except ValueError:
            self.selected_kit_ids.errors = ("Invalid kit IDs.",)
            return False

        return True
    
    def process_request(self):
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()

        for kit_id in self.kit_ids:
            kit = db.kits[kit_id]
            
            self.protocol.kits.append(kit)

        db.protocols.update(self.protocol)
        
        flash("Successfully added kits to protocol.", "success")
        return make_response(redirect=url_for("protocols_page.protocol", protocol_id=self.protocol.id))

