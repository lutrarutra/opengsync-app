import os
import shutil
from typing import Optional

import pandas as pd

from flask import Response, flash, url_for, current_app
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms import IntegerField, FieldList, FormField
from wtforms.validators import NumberRange, Optional as OptionalValidator, DataRequired

from limbless_db import models, DBHandler
from limbless_db.categories import FileType

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


class SubForm(FlaskForm):
    obj_id = IntegerField(validators=[DataRequired()])
    avg_fragment_size = IntegerField(validators=[OptionalValidator(), NumberRange(min=0)])


class CompleteBAReportForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/ba_report/bar-3.html"
    _form_label = "ba_report_form"

    pool_fields = FieldList(FormField(SubForm), min_entries=0)
    library_fields = FieldList(FormField(SubForm), min_entries=0)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None, previous_form: Optional[TableDataForm] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="ba_report", uuid=uuid, previous_form=previous_form)
        self._context["enumerate"] = enumerate
        
    def prepare(self):
        pool_table = self.tables["pool_table"]
        library_table = self.tables["library_table"]

        for i, (idx, row) in enumerate(pool_table.iterrows()):
            if i > len(self.pool_fields) - 1:
                self.pool_fields.append_entry()

            self.pool_fields[i].obj_id.data = row["id"]

            if pd.notna(pool_table.at[idx, "avg_fragment_size"]):
                self.pool_fields[i].avg_fragment_size.data = int(pool_table.at[idx, "avg_fragment_size"])

        for i, (idx, row) in enumerate(library_table.iterrows()):
            if i > len(self.library_fields) - 1:
                self.library_fields.append_entry()

            self.library_fields[i].obj_id.data = row["id"]

            if pd.notna(library_table.at[idx, "avg_fragment_size"]):
                self.library_fields[i].avg_fragment_size.data = int(library_table.at[idx, "avg_fragment_size"])

        self._context["pool_table"] = pool_table
        self._context["library_table"] = library_table
    
    def process_request(self, current_user: models.User) -> Response:
        if not self.validate():
            pool_table = self.tables["pool_table"]
            library_table = self.tables["library_table"]
            logger.debug(self.errors)
            return self.make_response(pool_table=pool_table, library_table=library_table)
        
        pool_table = self.tables["pool_table"]
        library_table = self.tables["library_table"]
        metadata = self.metadata.copy()
        ba_report = metadata["ba_report"]

        ba_report_path = os.path.join(self._dir, f"{ba_report['uuid']}{ba_report['extension']}")
        new_path = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.BIOANALYZER_REPORT.dir, f"{ba_report['uuid']}{ba_report['extension']}")
        shutil.copy(ba_report_path, new_path)
        os.remove(ba_report_path)
        size_bytes = os.stat(new_path).st_size

        ba_file = db.create_file(
            name=ba_report["filename"],
            extension=ba_report["extension"],
            size_bytes=size_bytes,
            type=FileType.BIOANALYZER_REPORT,
            uploader_id=current_user.id,
            uuid=ba_report['uuid'],
        )

        for sub_form in self.pool_fields:
            if (pool := db.get_pool(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Pool {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Pool {sub_form.obj_id.data} not found")
            
            pool.avg_fragment_size = sub_form.avg_fragment_size.data
            pool.ba_report_id = ba_file.id
            pool = db.update_pool(pool)

            pool_table.loc[pool_table["id"] == pool.id, "avg_fragment_size"] = pool.avg_fragment_size

        for sub_form in self.library_fields:
            if (library := db.get_library(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Library {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Library {sub_form.obj_id.data} not found")
            
            library.avg_fragment_size = sub_form.avg_fragment_size.data
            library.ba_report_id = ba_file.id
            library = db.update_library(library)

            library_table.loc[library_table["id"] == library.id, "avg_fragment_size"] = library.avg_fragment_size

        if os.path.exists(self.path):
            os.remove(self.path)

        flash("Pool QC data saved", "success")
        if (experiment_id := metadata.get("experiment_id")) is not None:
            return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment_id))
        
        return make_response(redirect=url_for("index_page"))