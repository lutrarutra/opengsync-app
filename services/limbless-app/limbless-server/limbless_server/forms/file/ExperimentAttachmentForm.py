import os
import uuid
from typing import Optional

from flask import Response, flash, url_for, current_app
from flask_htmx import make_response

from limbless_db import models
from limbless_db.categories import FileType
from .FileInputForm import FileInputForm
from ... import db, logger


class ExperimentAttachmentForm(FileInputForm):
    def __init__(self, experiment_id: int, formdata: Optional[dict] = None, max_size_mbytes: int = 5):
        FileInputForm.__init__(self, formdata=formdata, max_size_mbytes=max_size_mbytes)
        self._post_url = url_for("experiments_htmx.upload_file", experiment_id=experiment_id)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if FileType.get(self.file_type.data) == FileType.SEQ_AUTH_FORM:
            self.file_type.errors = ("Invalid file type for experiment.",)
            return False
            
        return True

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        user: models.User = context["user"]
        experiment: models.Experiment = context["experiment"]

        file_type = FileType.get(self.file_type.data)

        filename, extension = os.path.splitext(self.file.data.filename)

        _uuid = str(uuid.uuid4())
        filepath = os.path.join(current_app.config["MEDIA_FOLDER"], file_type.dir, f"{_uuid}{extension}")
        self.file.data.save(filepath)
        size_bytes = os.stat(filepath).st_size

        db_file = db.create_file(
            name=filename,
            type=file_type,
            extension=extension,
            uploader_id=user.id,
            size_bytes=size_bytes,
            uuid=_uuid
        )

        if self.comment.data and self.comment.data.strip() != "":
            comment = db.create_comment(
                text=self.comment.data,
                author_id=user.id,
                file_id=db_file.id
            )
            db.add_experiment_comment(experiment.id, comment.id)

        db.add_file_to_experiment(experiment.id, db_file.id)

        flash("File uploaded successfully.", "success")
        logger.info(f"File '{db_file.uuid}' uploaded by user '{user.id}'.")
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))
        
