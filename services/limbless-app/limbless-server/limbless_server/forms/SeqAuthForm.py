import os

from flask import Response, url_for, flash, current_app
from flask_htmx import make_response
from wtforms import FileField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed

from limbless_db.categories import FileType
from limbless_db import models
from .. import logger, db
from .HTMXFlaskForm import HTMXFlaskForm


class SeqAuthForm(HTMXFlaskForm):
    _template_path = "forms/seq_request/seq_auth.html"
    _form_label = "seq_auth_form"

    file = FileField("Sequencing Authorization Form", validators=[DataRequired(), FileAllowed(["pdf"])],)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        # Max size 3
        MAX_MBYTES = 3
        max_bytes = MAX_MBYTES * 1024 * 1024
        self.size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if self.size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {MAX_MBYTES} MB",)
            return False
        
        return True
    
    def process_request(self, **context) -> Response:
        seq_request: models.SeqRequest = context["seq_request"]
        if not self.validate():
            return self.make_response(**context)

        user: models.User = context["user"]

        filename, extension = os.path.splitext(self.file.data.filename)

        db_file = db.create_file(
            name=filename,
            type=FileType.SEQ_AUTH_FORM,
            extension=extension,
            uploader_id=user.id,
            size_bytes=self.size_bytes
        )

        filepath = os.path.join(current_app.config["MEDIA_FOLDER"], db_file.path)
        self.file.data.save(filepath)

        db.add_file_to_seq_request(seq_request.id, db_file.id)

        flash("Authorization form uploaded!", "success")
        logger.debug(f"Uploaded sequencing authorization form for sequencing request '{seq_request.name}': {filepath}")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
        )