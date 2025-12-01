from typing import Optional, Any

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import EmailField
from wtforms.validators import DataRequired, Length, Email

from opengsync_db import models
from .. import logger, db
from .HTMXFlaskForm import HTMXFlaskForm


class SeqRequestShareEmailForm(HTMXFlaskForm):
    _template_path = "components/popups/seq_request_share_email_form.html"

    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=models.links.SeqRequestDeliveryEmailLink.email.type.length)])

    def __init__(self, seq_request: models.SeqRequest, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)
        self.seq_request = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.email.data is None:
            self.email.errors = ("Please enter an email address.",)
            return False

        email = self.email.data.strip()
        
        if email in [link.email for link in self.seq_request.delivery_email_links]:
            self.email.errors = ("This email adress is already in the list.",)
            return False
        
        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        db.seq_requests.add_share_email(
            seq_request_id=self.seq_request.id,
            email=self.email.data.strip()  # type: ignore
        )

        flash("Email added to the list.", "success")
        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id, tab="request-share-tab"))