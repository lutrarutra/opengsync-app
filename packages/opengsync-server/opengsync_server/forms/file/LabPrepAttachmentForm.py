import os
from uuid6 import uuid7
from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import SelectField

from opengsync_db import models
from opengsync_db.categories import MediaFileType

from .FileInputForm import FileInputForm
from ... import db, logger
from ...core.RunTime import runtime


class LabPrepAttachmentForm(FileInputForm):
    file_type = SelectField("File Type", choices=[(ft.id, ft.display_name) for ft in [MediaFileType.BIOANALYZER_REPORT, MediaFileType.CUSTOM]], coerce=int, description="Select the type of file you are uploading.")

    def __init__(self, lab_prep: models.LabPrep, formdata: Optional[dict] = None, max_size_mbytes: int = 5):
        FileInputForm.__init__(self, formdata=formdata, max_size_mbytes=max_size_mbytes)
        self._post_url = url_for("lab_preps_htmx.file_form", lab_prep_id=lab_prep.id)
        self.lab_prep = lab_prep

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        file_type = MediaFileType.get(self.file_type.data)
        
        if file_type == MediaFileType.LIBRARY_PREP_FILE:
            self.file_type.errors = ("You must uploade library prep file through a workflow.",)
            return False
            
        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()

        file_type = MediaFileType.get(self.file_type.data)

        filename, extension = os.path.splitext(self.file.data.filename)

        _uuid = uuid7().__str__()
        filepath = os.path.join(runtime.app.media_folder, file_type.dir, f"{_uuid}{extension}")
        self.file.data.save(filepath)
        size_bytes = os.stat(filepath).st_size

        db_file = db.media_files.create(
            name=filename,
            type=file_type,
            extension=extension,
            uploader_id=user.id,
            size_bytes=size_bytes,
            uuid=_uuid,
            lab_prep_id=self.lab_prep.id
        )

        if self.comment.data and self.comment.data.strip() != "":
            _ = db.comments.create(
                text=self.comment.data,
                author_id=user.id,
                file_id=db_file.id,
                lab_prep_id=self.lab_prep.id
            )

        flash("File uploaded successfully.", "success")
        logger.info(f"File '{db_file.uuid}' uploaded by user '{user.id}'.")
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))

        
