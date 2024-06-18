from typing import Optional, Any

import pandas as pd
import json

from flask import Response
from wtforms import StringField

from limbless_db import models, DBSession

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from .StoreSamplesForm import StoreSamplesForm


class SelectSamplesForm(HTMXFlaskForm):
    _template_path = "workflows/store_samples/store-1.html"
    _form_label = "store_samples_form"

    selected_sample_ids = StringField()
    selected_library_ids = StringField()
    selected_pool_ids = StringField()

    error_dummy = StringField()

    def __init__(self, formdata: dict = {}, seq_request: Optional[models.SeqRequest] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["url_context"] = {}
        self.seq_request = seq_request
        if seq_request is not None:
            self._context["url_context"]["seq_request_id"] = seq_request.id
            self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        validated = super().validate()

        selected_sample_ids = self.selected_sample_ids.data
        selected_library_ids = self.selected_library_ids.data
        selected_pool_ids = self.selected_pool_ids.data
        
        if not selected_pool_ids and not selected_library_ids and not selected_sample_ids:
            self.error_dummy.errors = ["Select at least one sample"]
            return False

        if selected_sample_ids:
            sample_ids = json.loads(selected_sample_ids)
        else:
            sample_ids = []

        if selected_library_ids:
            library_ids = json.loads(selected_library_ids)
        else:
            library_ids = []

        if selected_pool_ids:
            pool_ids = json.loads(selected_pool_ids)
        else:
            pool_ids = []

        if len(pool_ids) + len(library_ids) + len(sample_ids) == 0:
            self.selected_pool_ids.errors = ["Select at least one sample"]
            return False
        
        self.sample_ids = []
        try:
            for sample_id in sample_ids:
                self.sample_ids.append(int(sample_id))
        except ValueError:
            self.selected_sample_ids.errors = ["Invalid sample id"]
            return False
        
        self.library_ids = []
        try:
            for library_id in library_ids:
                self.library_ids.append(int(library_id))
        except ValueError:
            self.selected_library_ids.errors = ["Invalid library id"]
            return False
        
        self.pool_ids = []
        try:
            for library_id in pool_ids:
                self.pool_ids.append(int(library_id))
        except ValueError:
            self.selected_pool_ids.errors = ["Invalid library id"]
            return False
        
        self._context["selected_samples"] = self.sample_ids
        self._context["selected_libraries"] = self.library_ids
        self._context["selected_pools"] = self.pool_ids
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        sample_data = dict(id=[], name=[], status_id=[])
        library_data = dict(id=[], name=[], status_id=[])
        pool_data = dict(id=[], name=[], status_id=[])

        with DBSession(db) as session:
            for sample_id in self.sample_ids:
                if (sample := session.get_sample(sample_id)) is None:
                    logger.error(f"Sample {sample_id} not found")
                    raise ValueError(f"Sample {sample_id} not found")
                
                sample_data["id"].append(sample.id)
                sample_data["name"].append(sample.name)
                sample_data["status_id"].append(sample.status_id)

            for library_id in self.library_ids:
                if (library := session.get_library(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")

                library_data["id"].append(library.id)
                library_data["name"].append(library.name)
                library_data["status_id"].append(library.status_id)

            for pool_id in self.pool_ids:
                if (pool := session.get_pool(pool_id)) is None:
                    logger.error(f"Pool {pool_id} not found")
                    raise ValueError(f"Pool {pool_id} not found")

                pool_data["id"].append(pool.id)
                pool_data["name"].append(pool.name)
                pool_data["status_id"].append(pool.status_id)

        store_samples_form = StoreSamplesForm(seq_request=self.seq_request)
        store_samples_form.metadata = {"workflow": "store_samples"}
        if self.seq_request is not None:
            store_samples_form.metadata["seq_request_id"] = self.seq_request.id  # type: ignore
        store_samples_form.add_table("sample_table", pd.DataFrame(sample_data))
        store_samples_form.add_table("library_table", pd.DataFrame(library_data))
        store_samples_form.add_table("pool_table", pd.DataFrame(pool_data))
        store_samples_form.update_data()
        
        store_samples_form.prepare()
        return store_samples_form.make_response()