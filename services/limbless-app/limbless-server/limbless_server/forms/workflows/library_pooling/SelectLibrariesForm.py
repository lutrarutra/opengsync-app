from typing import Optional

import pandas as pd
import json

from flask import Response
from wtforms import StringField
from .BarcodeInputForm import BarcodeInputForm

from limbless_db import DBSession

from .... import logger, db
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


class SelectLibrariesForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_pooling/pooling-2.html"
    _form_label = "library_pooling_form"

    selected_library_ids = StringField()

    def __init__(self, seq_request_id: Optional[int] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_pooling", uuid=uuid)
        if seq_request_id is not None:
            self._context["seq_request_id"] = seq_request_id

    def validate(self) -> bool:
        validated = super().validate()

        if not (selected_library_ids := self.selected_library_ids.data):
            self.selected_library_ids.errors = ["Select at least one library"]
            return False
        
        if len(ids := json.loads(selected_library_ids)) < 1:
            self.selected_library_ids.errors = ["Select at least one library"]
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
                if (library := session.get_library(library_id)) is None:
                    logger.error(f"{self.uuid}: Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")
                
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