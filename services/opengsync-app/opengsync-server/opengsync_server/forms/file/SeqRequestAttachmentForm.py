import os
from uuid_extensions import uuid7str
from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import SelectField

from opengsync_db import models
from opengsync_db.categories import MediaFileType

from .FileInputForm import FileInputForm
from ... import db, logger
from ...core.RunTime import runtime


class SeqRequestAttachmentForm(FileInputForm):
    file_type = SelectField("File Type", choices=[(ft.id, ft.display_name) for ft in [MediaFileType.SEQ_AUTH_FORM, MediaFileType.CUSTOM]], coerce=int, description="Select the type of file you are uploading.")
    
    def __init__(self, seq_request: models.SeqRequest, formdata: Optional[dict] = None, max_size_mbytes: int = 5):
        FileInputForm.__init__(self, formdata=formdata, max_size_mbytes=max_size_mbytes)
        self.seq_request = seq_request
        self._post_url = url_for("seq_requests_htmx.file_form", seq_request_id=seq_request.id)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if MediaFileType.get(self.file_type.data) == MediaFileType.SEQ_AUTH_FORM:
            if self.seq_request.seq_auth_form_file is not None:
                self.file_type.errors = ("Authorization form has already been uploaded. Please, delete it first before continuing.",)
                return False
        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()

        file_type = MediaFileType.get(self.file_type.data)

        filename, extension = os.path.splitext(self.file.data.filename)

        _uuid = uuid7str()
        filepath = os.path.join(runtime.app.media_folder, file_type.dir, f"{_uuid}{extension}")
        self.file.data.save(filepath)
        size_bytes = os.stat(filepath).st_size

        db_file = db.files.create(
            name=filename,
            type=file_type,
            extension=extension,
            uploader_id=user.id,
            size_bytes=size_bytes,
            uuid=_uuid,
            seq_request_id=self.seq_request.id
        )

        if self.comment.data and self.comment.data.strip() != "":
            _ = db.comments.create(
                text=self.comment.data,
                author_id=user.id,
                file_id=db_file.id,
                seq_request_id=self.seq_request.id
            )

        flash("File uploaded successfully.", "success")
        logger.info(f"File '{db_file.uuid}' uploaded by user '{user.id}'.")
        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id))
        
