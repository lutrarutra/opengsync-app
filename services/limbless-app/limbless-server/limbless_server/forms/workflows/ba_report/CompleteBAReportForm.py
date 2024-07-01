import os
import shutil
import uuid
from typing import Optional

import pandas as pd

from flask import Response, flash, url_for, current_app
from flask_wtf.file import FileField, FileAllowed
from flask_htmx import make_response
from wtforms.validators import NumberRange, DataRequired
from wtforms import IntegerField, FieldList, FormField
from flask_wtf import FlaskForm

from limbless_db import models, DBSession
from limbless_db.categories import PoolStatus, FileType, LibraryStatus, SampleStatus

from .... import db, logger  # noqa
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm


class SubForm(FlaskForm):
    obj_id = IntegerField(validators=[DataRequired()])
    avg_fragment_size = IntegerField(validators=[DataRequired(), NumberRange(min=0)])


class CompleteBAReportForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/ba_report/bar-1.html"
    _form_label = "ba_report_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("pdf", "PDF"),
    ]

    sample_fields = FieldList(FormField(SubForm), min_entries=0)
    library_fields = FieldList(FormField(SubForm), min_entries=0)
    pool_fields = FieldList(FormField(SubForm), min_entries=0)
    lane_fields = FieldList(FormField(SubForm), min_entries=0)

    file = FileField("Bio Analyzer Report", validators=[DataRequired(), FileAllowed([ext for ext, _ in _allowed_extensions])], description="Report exported from the BioAnalyzer software (pdf).")

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None, max_size_mbytes: int = 5):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="ba_report", uuid=uuid)
        self.max_size_mbytes = max_size_mbytes
        self._context["enumerate"] = enumerate

    def prepare(self):
        sample_table = self.tables["sample_table"]
        library_table = self.tables["library_table"]
        pool_table = self.tables["pool_table"]
        lane_table = self.tables["lane_table"]

        for i, (idx, row) in enumerate(sample_table.iterrows()):
            if i > len(self.sample_fields) - 1:
                self.sample_fields.append_entry()

            self.sample_fields[i].obj_id.data = row["id"]

            if pd.notna(sample_table.at[idx, "avg_fragment_size"]):
                self.sample_fields[i].avg_fragment_size.data = int(sample_table.at[idx, "avg_fragment_size"])

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

        for i, (idx, row) in enumerate(lane_table.iterrows()):
            if i > len(self.lane_fields) - 1:
                self.lane_fields.append_entry()

            self.lane_fields[i].obj_id.data = row["id"]

            if pd.notna(lane_table.at[idx, "avg_fragment_size"]):
                self.lane_fields[i].avg_fragment_size.data = int(lane_table.at[idx, "avg_fragment_size"])

        self._context["sample_table"] = sample_table
        self._context["library_table"] = library_table
        self._context["pool_table"] = pool_table
        self._context["lane_table"] = lane_table
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        max_bytes = self.max_size_mbytes * 1024 * 1024
        size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {self.max_size_mbytes} MB",)
            return False
        
        return True
    
    def process_request(self, user: models.User) -> Response:
        sample_table = self.tables["sample_table"]
        library_table = self.tables["library_table"]
        pool_table = self.tables["pool_table"]
        lane_table = self.tables["lane_table"]

        if not self.validate():
            return self.make_response(
                sample_table=sample_table,
                library_table=library_table,
                pool_table=pool_table,
                lane_table=lane_table,
            )
        
        metadata = self.metadata.copy()

        filename, extension = os.path.splitext(self.file.data.filename)
        
        _uuid = str(uuid.uuid4())
        filepath = os.path.join(self._dir, f"{_uuid}{extension}")
        self.file.data.save(filepath)

        ba_report_path = os.path.join(self._dir, f"{_uuid}{extension}")
        new_path = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.BIOANALYZER_REPORT.dir, f"{_uuid}{extension}")
        shutil.copy(ba_report_path, new_path)
        os.remove(ba_report_path)
        size_bytes = os.stat(new_path).st_size

        ba_file = db.create_file(
            name=filename,
            extension=extension,
            size_bytes=size_bytes,
            type=FileType.BIOANALYZER_REPORT,
            uploader_id=user.id,
            uuid=_uuid,
        )

        self.metadata["ba_report"] = {
            "filename": filename,
            "extension": extension,
            "uuid": _uuid,
        }

        for sub_form in self.sample_fields:
            if (sample := db.get_sample(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Sample {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Sample {sub_form.obj_id.data} not found")
            
            sample.avg_fragment_size = sub_form.avg_fragment_size.data
            sample.ba_report_id = ba_file.id
            sample = db.update_sample(sample)

            sample_table.loc[sample_table["id"] == sample.id, "avg_fragment_size"] = sample.avg_fragment_size

        for sub_form in self.library_fields:
            if (library := db.get_library(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Library {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Library {sub_form.obj_id.data} not found")
            
            library.avg_fragment_size = sub_form.avg_fragment_size.data
            library.ba_report_id = ba_file.id
                            
            library = db.update_library(library)

            library_table.loc[library_table["id"] == library.id, "avg_fragment_size"] = library.avg_fragment_size

        for sub_form in self.pool_fields:
            with DBSession(db) as session:
                if (pool := session.get_pool(sub_form.obj_id.data)) is None:
                    logger.error(f"{self.uuid}: Pool {sub_form.obj_id.data} not found")
                    raise ValueError(f"{self.uuid}: Pool {sub_form.obj_id.data} not found")
                
                pool.avg_fragment_size = sub_form.avg_fragment_size.data
                pool.ba_report_id = ba_file.id

                if pool.avg_fragment_size is not None:
                    for library in pool.libraries:
                        if library.is_pooled():
                            library.status_id = LibraryStatus.POOLED.id
                            for sample_link in library.sample_links:
                                sample_is_prepped = True
                                for library_link in sample_link.sample.library_links:
                                    if library_link.library != library and not library_link.library.is_indexed():
                                        sample_is_prepped = False
                                        break
                                if sample_is_prepped:
                                    sample_link.sample.status_id = SampleStatus.PREPARED.id

                if pool.status == PoolStatus.ACCEPTED:
                    pool.status_id = PoolStatus.STORED.id

                pool = session.update_pool(pool)

            pool_table.loc[pool_table["id"] == pool.id, "avg_fragment_size"] = pool.avg_fragment_size

        for sub_form in self.lane_fields:
            if (lane := db.get_lane(sub_form.obj_id.data)) is None:
                logger.error(f"{self.uuid}: Lane {sub_form.obj_id.data} not found")
                raise ValueError(f"{self.uuid}: Lane {sub_form.obj_id.data} not found")
            
            lane.avg_fragment_size = sub_form.avg_fragment_size.data
            lane.ba_report_id = ba_file.id
            lane = db.update_lane(lane)

            lane_table.loc[lane_table["id"] == lane.id, "avg_fragment_size"] = lane.avg_fragment_size

        if os.path.exists(self.path):
            os.remove(self.path)

        flash("Qubit Measurements saved!", "success")
        if (experiment_id := metadata.get("experiment_id")) is not None:
            return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment_id))
        
        return make_response(redirect=url_for("index_page"))