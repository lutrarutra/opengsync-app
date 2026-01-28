import os
import pandas as pd
from uuid_extensions import uuid7str

from flask import Response, flash, url_for
from flask_wtf.file import FileField, FileAllowed
from flask_htmx import make_response
from wtforms.validators import NumberRange, DataRequired, Optional as OptionalValidator
from wtforms import IntegerField, FieldList, FormField, StringField
from flask_wtf import FlaskForm

from opengsync_db import models
from opengsync_db.categories import MediaFileType, PoolStatus

from .... import db, logger
from ....core import exceptions
from ....core.RunTime import runtime
from ...MultiStepForm import MultiStepForm


class SubForm(FlaskForm):
    obj_id = IntegerField(validators=[DataRequired()])
    sample_type = StringField(validators=[DataRequired()])
    avg_fragment_size = IntegerField(validators=[OptionalValidator(), NumberRange(min=0)])


class CompleteBAForm(MultiStepForm):
    _template_path = "workflows/ba_report/bar-3.html"
    _workflow_name = "ba_report"
    _step_name = "complete_ba_form"

    sample_fields = FieldList(FormField(SubForm), min_entries=0)
    report = FileField("Bio Analyzer Report", validators=[DataRequired(), FileAllowed(["pdf"])], description="Report exported from the BioAnalyzer software (pdf).")

    def __init__(self, uuid: str | None, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=CompleteBAForm._workflow_name,
            step_name=CompleteBAForm._step_name, uuid=uuid, formdata=formdata,
            step_args={}
        )
        self.ba_table = self.tables["ba_table"]
        self._context["enumerate"] = enumerate

    def prepare(self):
        for i, (idx, row) in enumerate(self.ba_table.iterrows()):
            if i > len(self.sample_fields) - 1:
                self.sample_fields.append_entry()

            self.sample_fields[i].obj_id.data = int(row["id"])
            self.sample_fields[i].sample_type.data = row["sample_type"]

            if pd.notna(fragment_size := self.ba_table.at[idx, "avg_fragment_size"]):
                self.sample_fields[i].avg_fragment_size.data = int(fragment_size)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True
    
    @classmethod
    def save_changes(cls, metadata: dict, report, user: models.User, uuid: str, sample_fields: list[SubForm]):
        metadata = metadata.copy()
        filename, extension = os.path.splitext(report.data.filename)
        
        file_uuid = uuid7str()
        new_path = os.path.join(runtime.app.media_folder, MediaFileType.BIOANALYZER_REPORT.dir, f"{file_uuid}{extension}")
        report.data.save(new_path)
        size_bytes = os.stat(new_path).st_size

        if (lab_prep_id := metadata.get("lab_prep_id")) is not None:
            if db.lab_preps.get(lab_prep_id) is None:
                logger.error(f"{uuid}: lab_prep_id {lab_prep_id} not found")
                raise ValueError(f"{uuid}: lab_prep_id {lab_prep_id} not found")
            
        ba_file = db.media_files.create(
            name=filename,
            extension=extension,
            size_bytes=size_bytes,
            type=MediaFileType.BIOANALYZER_REPORT,
            uploader_id=user.id,
            uuid=file_uuid,
            lab_prep_id=lab_prep_id
        )

        metadata["ba_report"] = {
            "filename": filename,
            "extension": extension,
            "uuid": file_uuid,
        }

        for sub_form in sample_fields:
            obj_id = int(sub_form.obj_id.data)  # type: ignore

            match sub_form.sample_type.data:
                case "sample":
                    if (sample := db.samples.get(obj_id)) is None:
                        logger.error(f"{uuid}: Sample {sub_form.obj_id.data} not found")
                        raise ValueError(f"{uuid}: Sample {sub_form.obj_id.data} not found")

                    if sub_form.avg_fragment_size.data is None:
                        sample.ba_report = None
                        sample.avg_fragment_size = None
                    else:
                        sample.avg_fragment_size = sub_form.avg_fragment_size.data
                        sample.ba_report = ba_file
                    db.samples.update(sample)
                case "library":
                    if (library := db.libraries.get(obj_id)) is None:
                        logger.error(f"{uuid}: Library {obj_id} not found")
                        raise ValueError(f"{uuid}: Library {obj_id} not found")

                    if sub_form.avg_fragment_size.data is None:
                        library.ba_report = None
                        library.avg_fragment_size = None
                    else:
                        library.avg_fragment_size = sub_form.avg_fragment_size.data
                        library.ba_report = ba_file
                    db.libraries.update(library)
                case "pool":
                    if (pool := db.pools.get(obj_id)) is None:
                        logger.error(f"{uuid}: Pool {obj_id} not found")
                        raise ValueError(f"{uuid}: Pool {obj_id} not found")

                    if sub_form.avg_fragment_size.data is None:
                        pool.ba_report_id = None
                        pool.avg_fragment_size = None
                    else:
                        pool.avg_fragment_size = sub_form.avg_fragment_size.data
                        pool.ba_report_id = ba_file.id
                        if pool.status == PoolStatus.ACCEPTED:
                            pool.status = PoolStatus.STORED
                    db.pools.update(pool)
                case "lane":
                    if (lane := db.lanes.get(obj_id)) is None:
                        logger.error(f"{uuid}: Lane {obj_id} not found")
                        raise ValueError(f"{uuid}: Lane {obj_id} not found")

                    if sub_form.avg_fragment_size.data is None:
                        lane.ba_report_id = None
                        lane.avg_fragment_size = None
                    else:
                        lane.avg_fragment_size = sub_form.avg_fragment_size.data
                        lane.ba_report_id = ba_file.id
                    db.lanes.update(lane)
                case _:
                    logger.error(f"{uuid}: Invalid sample_type {sub_form.sample_type.data}")
                    raise exceptions.InternalServerErrorException(f"{uuid}: Invalid sample_type {sub_form.sample_type.data}")
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()

        self.save_changes(
            user=user,
            metadata=self.metadata,
            report=self.report,
            uuid=self.uuid,
            sample_fields=self.sample_fields,  # type: ignore
        )

        if (experiment_id := self.metadata.get("experiment_id")) is not None:
            url = url_for("experiments_page.experiment", experiment_id=experiment_id)
        elif (seq_request_id := self.metadata.get("seq_request_id")) is not None:
            url = url_for("seq_requests_page.seq_request", seq_request_id=seq_request_id)
        elif (pool_id := self.metadata.get("pool_id")) is not None:
            url = url_for("pools_page.pool", pool_id=pool_id)
        elif (lab_prep_id := self.metadata.get("lab_prep_id")) is not None:
            url = url_for("lab_preps_page.lab_prep", lab_prep_id=lab_prep_id)
        else:
            url = url_for("dashboard")

        self.complete()
        flash("Changes Saved!", "success")
        return make_response(redirect=url)