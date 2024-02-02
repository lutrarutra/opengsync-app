import os
from uuid import uuid4

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import FileField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed

from .. import SEQ_AUTH_FORMS_DIR, logger, models, db
from .HTMXFlaskForm import HTMXFlaskForm


class SeqAuthForm(HTMXFlaskForm):
    _template_path = "forms/seq_request/seq_auth.html"
    _form_label = "seq_auth_form"

    file = FileField(
        "Sequencing Authorization Form",
        validators=[DataRequired(), FileAllowed(["pdf"])],
    )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        # Max size 3
        MAX_MBYTES = 3
        max_bytes = MAX_MBYTES * 1024 * 1024
        size_bytes = len(self.file.data.read())
        self.file.data.seek(0)

        if size_bytes > max_bytes:
            self.file.errors = (f"File size exceeds {MAX_MBYTES} MB",)
            return False
        
        return True
    
    def process_request(self, **context) -> Response:
        seq_request: models.SeqRequest = context["seq_request"]
        if not self.validate():
            return self.make_response(**context)
        
        uuid = str(uuid4())
        filepath = os.path.join(SEQ_AUTH_FORMS_DIR, f"{uuid}.pdf")
        self.file.data.save(filepath)

        seq_request.seq_auth_form_uuid = uuid
        seq_request = db.db_handler.update_seq_request(seq_request=seq_request)

        flash("Authorization form uploaded!", "success")
        logger.debug(f"Uploaded sequencing authorization form for sequencing request '{seq_request.name}': {uuid}")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
        )