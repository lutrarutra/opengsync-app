from typing import Optional, Any

import pandas as pd
import json

from flask import Response
from wtforms import StringField, IntegerField

from limbless_db import models, DBSession

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm


class SelectSamplesForm(HTMXFlaskForm):
    _template_path = "workflows/plate_samples/store-1.html"
    _form_label = "plate_samples_form"

    selected_sample_ids = StringField()

    error_dummy = StringField()

    def __init__(self, formdata: dict = {}, seq_request: Optional[models.SeqRequest] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["url_context"] = {}
        if seq_request is not None:
            self._context["url_context"]["seq_request_id"] = seq_request.id
            self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        validated = super().validate()

        selected_sample_ids = self.selected_sample_ids.data
        
        if not selected_sample_ids:
            self.error_dummy.errors = ["Select at least sample"]
            return False

        if selected_sample_ids:
            sample_ids = json.loads(selected_sample_ids)
        else:
            sample_ids = []
        
        if len(sample_ids) == 0:
            self.selected_sample_ids.errors = ["Select at least one sample"]
            return False
        
        self.sample_ids = []
        try:
            for sample_id in sample_ids:
                self.sample_ids.append(int(sample_id))
        except ValueError:
            self.selected_sample_ids.errors = ["Invalid sample id"]
            return False
        
        self._context["selected_samples"] = self.sample_ids
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        sample_data = dict(
            id=[], name=[],
            qubit_concentration=[],
        )

        with DBSession(db) as session:
            for sample_id in self.sample_ids:
                if (sample := session.get_sample(sample_id)) is None:
                    logger.error(f"Sample {sample_id} not found")
                    raise ValueError(f"Sample {sample_id} not found")
                
                sample_data["id"].append(sample.id)
                sample_data["name"].append(sample.name)
                sample_data["library_ids"] = [link.library.type.id for link in sample.library_links]

        complete_qubit_measure_form = CompleteQubitMeasureForm()
        metadata: dict[str, Any] = {
            "workflow": "qubit_measure",
        }

        complete_qubit_measure_form.metadata = metadata
        
        complete_qubit_measure_form.add_table("sample_data", pd.DataFrame(sample_data))

        complete_qubit_measure_form.update_data()
        complete_qubit_measure_form.prepare()
        return complete_qubit_measure_form.make_response()