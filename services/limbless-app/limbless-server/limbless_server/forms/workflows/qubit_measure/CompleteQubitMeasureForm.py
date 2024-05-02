import os
from typing import Optional

import pandas as pd

from flask import Response, flash, url_for
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms import FloatField, IntegerField, FieldList, FormField
from wtforms.validators import NumberRange, Optional as OptionalValidator, DataRequired

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


class SubForm(FlaskForm):
    obj_id = IntegerField(validators=[DataRequired()])
    qubit_concentration = FloatField(validators=[OptionalValidator(), NumberRange(min=0)])


class CompleteQubitMeasureForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/qubit_measure/qubit-2.html"
    _form_label = "qubit_measure_form"

    pool_fields = FieldList(FormField(SubForm), min_entries=0)
    library_fields = FieldList(FormField(SubForm), min_entries=0)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None, previous_form: Optional[TableDataForm] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="qubit_measure", uuid=uuid, previous_form=previous_form)
        self._context["enumerate"] = enumerate
        
    def prepare(self):
        pool_table = self.tables["pool_table"]
        library_table = self.tables["library_table"]

        for i, (idx, row) in enumerate(pool_table.iterrows()):
            if i > len(self.pool_fields) - 1:
                self.pool_fields.append_entry()

            self.pool_fields[i].obj_id.data = row["id"]

            if pd.notna(pool_table.at[idx, "qubit_concentration"]):
                self.pool_fields[i].qubit_concentration.data = int(pool_table.at[idx, "qubit_concentration"])

        for i, (idx, row) in enumerate(library_table.iterrows()):
            if i > len(self.library_fields) - 1:
                self.library_fields.append_entry()

            self.library_fields[i].obj_id.data = row["id"]

            if pd.notna(library_table.at[idx, "qubit_concentration"]):
                self.library_fields[i].qubit_concentration.data = int(library_table.at[idx, "qubit_concentration"])

        self._context["pool_table"] = pool_table
        self._context["library_table"] = library_table
    
    def process_request(self) -> Response:
        if not self.validate():
            pool_table = self.tables["pool_table"]
            library_table = self.tables["library_table"]
            logger.debug(self.errors)
            return self.make_response(pool_table=pool_table, library_table=library_table)
        
        pool_table = self.tables["pool_table"]
        library_table = self.tables["library_table"]
        metadata = self.metadata.copy()

        for sub_form in self.pool_fields:
            if (pool := db.get_pool(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Pool {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Pool {sub_form.obj_id.data} not found")
            
            pool.qubit_concentration = sub_form.qubit_concentration.data
            pool = db.update_pool(pool)

            pool_table.loc[pool_table["id"] == pool.id, "qubit_concentration"] = pool.qubit_concentration

        for sub_form in self.library_fields:
            if (library := db.get_library(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Library {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Library {sub_form.obj_id.data} not found")
            
            library.qubit_concentration = sub_form.qubit_concentration.data
            library = db.update_library(library)

            library_table.loc[library_table["id"] == library.id, "qubit_concentration"] = library.qubit_concentration

        if os.path.exists(self.path):
            os.remove(self.path)

        flash("Qubit Measurements saved!", "success")
        if (experiment_id := metadata.get("experiment_id")) is not None:
            return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment_id))
        
        return make_response(redirect=url_for("index_page"))