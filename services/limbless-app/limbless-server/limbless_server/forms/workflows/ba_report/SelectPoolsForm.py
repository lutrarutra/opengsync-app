import pandas as pd
import json

from flask import Response
from wtforms import StringField

from limbless_db import models, DBSession

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from .BAInputForm import BAInputForm


class SelectPoolsForm(HTMXFlaskForm):
    _template_path = "workflows/ba_report/bar-1.html"
    _form_label = "ba_report_form"

    selected_pool_ids = StringField()

    def validate(self) -> bool:
        validated = super().validate()

        if not (selected_pool_ids := self.selected_pool_ids.data):
            self.selected_pool_ids.errors = ["Select at least one pool"]
            return False
        
        if len(ids := json.loads(selected_pool_ids)) < 1:
            self.selected_pool_ids.errors = ["Select at least one pool"]
            return False
        
        self.pool_ids = []
        try:
            for library_id in ids:
                self.pool_ids.append(int(library_id))
        except ValueError:
            self.selected_pool_ids.errors = ["Invalid library id"]
            return False

        self._context["selected_pools"] = self.pool_ids
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        pool_data = dict(
            id=[],
            name=[],
            avg_library_size=[],
        )

        with DBSession(db) as session:
            for pool_id in self.pool_ids:
                if (pool := session.get_pool(pool_id)) is None:
                    logger.error(f"Pool {pool_id} not found")
                    raise ValueError(f"Pool {pool_id} not found")
                
                pool_data["id"].append(pool.id)
                pool_data["name"].append(pool.name)
                pool_data["avg_library_size"].append(pool.avg_library_size)

        pool_table = pd.DataFrame(pool_data)

        ba_input_form = BAInputForm()
        ba_input_form.metadata = {
            "workflow": "ba_report",
        }
        ba_input_form.add_table("pool_table", pool_table)
        ba_input_form.update_data()
        ba_input_form.prepare()
        return ba_input_form.make_response()