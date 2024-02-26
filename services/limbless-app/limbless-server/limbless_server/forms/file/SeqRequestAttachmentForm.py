import os
from typing import Optional

from flask import Response, flash, url_for, current_app
from flask_htmx import make_response

from limbless_db import models
from limbless_db.core.categories import FileType
from .FileInputForm import FileInputForm
from ... import db, logger


class SeqRequestAttachmentForm(FileInputForm):
    def __init__(self, seq_request_id: int, formdata: Optional[dict] = None, max_size_mbytes: int = 5):
        FileInputForm.__init__(self, formdata=formdata, max_size_mbytes=max_size_mbytes)
        self._post_url = url_for("seq_requests_htmx.upload_file", seq_request_id=seq_request_id)

    def validate(self, seq_request: models.SeqRequest) -> bool:
        if not super().validate():
            return False
        
        if FileType.get(self.file_type.data) == FileType.SEQ_AUTH_FORM:
            if seq_request.seq_auth_form_file_id is not None:
                self.file_type.errors = ("A file of this type has already been uploaded.",)
                return False
        return True

    def process_request(self, **context) -> Response:
        user: models.User = context["user"]
        seq_request: models.SeqRequest = context["seq_request"]

        if not self.validate(seq_request):
            return self.make_response(**context)

        file_type = FileType.get(self.file_type.data)

        filename, extension = os.path.splitext(self.file.data.filename)
        
        db_file = db.create_file(
            name=filename,
            type=file_type,
            extension=extension,
            uploader_id=user.id,
        )

        if self.comment.data and self.comment.data.strip() != "":
            comment = db.create_comment(
                text=self.comment.data,
                author_id=user.id,
                file_id=db_file.id
            )
            db.add_seq_request_comment(seq_request.id, comment.id)

        filepath = os.path.join(current_app.config["MEDIA_FOLDER"], db_file.path)
        self.file.data.save(filepath)

        db.add_file_to_seq_request(seq_request.id, db_file.id)

        flash("File uploaded successfully.", "success")
        logger.info(f"File '{db_file.uuid}' uploaded by user '{user.id}'.")
        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))
        
