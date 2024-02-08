import os
from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response

from .FileInputForm import FileInputForm
from ...categories import FileType
from ... import models, db, logger


class SeqRequestFileForm(FileInputForm):
    def __init__(self, seq_request_id: int, formdata: Optional[dict] = None, max_size_mbytes: int = 5):
        FileInputForm.__init__(self, formdata=formdata, max_size_mbytes=max_size_mbytes)
        self._post_url = url_for("seq_requests_htmx.upload_file", seq_request_id=seq_request_id)

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        user: models.User = context["user"]
        seq_request: models.SeqRequest = context["seq_request"]

        file_type = FileType.get(self.file_type.data)

        filename, extension = os.path.splitext(self.file.data.filename)
        
        db_file = db.db_handler.create_file(
            name=filename,
            type=file_type,
            extension=extension,
            uploader_id=user.id
        )

        self.file.data.save(db_file.path)

        db.db_handler.add_file_to_seq_request(seq_request.id, db_file.id)

        flash("File uploaded successfully.", "success")
        logger.info(f"File '{db_file.uuid}' uploaded by user '{user.id}'.")
        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))
        
