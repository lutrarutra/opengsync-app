from typing import Optional

import pandas as pd
import json

from flask import Response
from wtforms import StringField
from .BarcodeInputForm import BarcodeInputForm

from limbless_db import models, DBSession

from .... import logger, db
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


class SelectLibrariesForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_pooling/pooling-2.html"
    _form_label = "library_pooling_form"

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "ok": "#82E0AA"
    }

    selected_library_ids = StringField()

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)

    def validate(self) -> bool:
        validated = super().validate()

        if not (selected_library_ids := self.selected_library_ids.data):
            self.selected_library_ids.errors = ["Please select atleast one library"]
            return False
        
        if len(ids := json.loads(selected_library_ids)) < 1:
            self.selected_library_ids.errors = ["Please select atleast one library"]
            return False
        
        self.library_ids = []
        try:
            for library_id in ids:
                self.library_ids.append(int(library_id))
        except ValueError:
            self.selected_library_ids.errors = ["Invalid library id"]
            return False

        self._context["selected_libraries"] = self.library_ids
        return validated

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response()

        barcode_data = dict(
            library_id=[],
            library_name=[],
            library_type=[],
            genome_ref=[],
            seq_depth_requested=[],
        )
        with DBSession(db) as session:
            for library_id in self.library_ids:
                library = session.get_library(library_id)
                barcode_data["library_id"].append(library.id)
                barcode_data["library_name"].append(library.name)
                barcode_data["library_type"].append(library.type.name)
                barcode_data["genome_ref"].append(library.genome_ref.name if library.genome_ref else None)
                barcode_data["seq_depth_requested"].append(library.seq_depth_requested)

        barcode_table = pd.DataFrame(barcode_data)
        barcode_table["kit"] = None
        barcode_table["adapter"] = None
        barcode_table["index_1"] = None
        barcode_table["index_2"] = None
        barcode_table["index_3"] = None
        barcode_table["index_4"] = None

        barcode_input_form = BarcodeInputForm(uuid=self.uuid, previous_form=self)
        barcode_input_form.add_table("barcode_table", barcode_table)
        barcode_input_form.update_data()
        barcode_input_form.prepare()

        return barcode_input_form.make_response(**context)