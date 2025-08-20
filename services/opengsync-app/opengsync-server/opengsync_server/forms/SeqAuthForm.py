import os
from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import FileField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed

from opengsync_db.categories import FileType
from opengsync_db import models

from .. import logger, db
from ..core.RunTime import runtime
from .HTMXFlaskForm import HTMXFlaskForm


class SeqAuthForm(HTMXFlaskForm):
    _template_path = "forms/seq_request/seq_auth.html"
    _form_label = "seq_auth_form"

    file = FileField("Sequencing Authorization Form", validators=[DataRequired(), FileAllowed(["pdf"])],)
    
    def __init__(self, seq_request: models.SeqRequest, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.seq_request.seq_auth_form_file is not None:
            self.file.errors = ("Authorization form has already been uploaded. Please, delete it first before continuing.",)
            return False
        
        MAX_MBYTES = 5
        max_bytes = MAX_MBYTES * 1024 * 1024
        self.size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if self.size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {MAX_MBYTES} MB",)
            return False
        
        return True
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()

        filename, extension = os.path.splitext(self.file.data.filename)

        db_file = db.files.create(
            name=filename,
            type=FileType.SEQ_AUTH_FORM,
            extension=extension,
            uploader_id=user.id,
            size_bytes=self.size_bytes,
            seq_request_id=self.seq_request.id,
        )
        filepath = os.path.join(runtime.current_app.media_folder, db_file.path)
        self.file.data.save(filepath)

        flash("Authorization form uploaded!", "success")
        logger.debug(f"Uploaded sequencing authorization form for sequencing request '{self.seq_request.name}': {filepath}")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id),
        )