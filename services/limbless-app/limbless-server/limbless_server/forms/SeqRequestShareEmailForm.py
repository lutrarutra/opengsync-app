from typing import Optional, Any

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import EmailField
from wtforms.validators import DataRequired, Length, Email

from limbless_db import models, DBSession
from .. import logger, db
from .HTMXFlaskForm import HTMXFlaskForm


class SeqRequestShareEmailForm(HTMXFlaskForm):
    _template_path = "components/popups/seq_request_share_email_form.html"
    _form_label = "seq_request_share_email_form"

    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=models.links.SeqRequestDeliveryEmailLink.email.type.length)])

    def __init__(self, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)

    def validate(self, seq_request_id: int) -> bool:
        if not super().validate():
            return False
        
        if self.email.data is None:
            self.email.errors = ("Please enter an email address.",)
            return False
        
        with DBSession(db) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                logger.error(f"SeqRequest with id '{seq_request_id}' not found.")
                raise ValueError(f"SeqRequest with id '{seq_request_id}' not found.")

            email = self.email.data.strip()
            
            if email in [link.email for link in seq_request.delivery_email_links]:
                self.email.errors = ("This email adress is already in the list.",)
                return False
        
        return True

    def process_request(self, **context) -> Response:
        seq_request = context["seq_request"]

        if not self.validate(seq_request_id=seq_request.id):
            return self.make_response(**context)
        
        db.add_seq_request_share_email(seq_request_id=seq_request.id, email=self.email.data.strip())  # type: ignore

        flash("Email added to the list.", "success")
        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))