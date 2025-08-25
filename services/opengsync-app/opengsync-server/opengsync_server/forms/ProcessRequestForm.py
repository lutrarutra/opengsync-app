from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import TextAreaField, EmailField, SelectField
from wtforms.validators import Optional as OptionalValidator, DataRequired, Length

from opengsync_db import models
from opengsync_db.categories import RequestResponse, SeqRequestStatus

from .. import logger, db  # noqa
from .HTMXFlaskForm import HTMXFlaskForm
from ..core import exceptions


class ProcessRequestForm(HTMXFlaskForm):
    _template_path = "forms/process_request.html"
    _form_label = "process_request_form"

    response_type = SelectField("Response", choices=[(-1, "")] + RequestResponse.as_selectable(), validators=[DataRequired()], default=None, coerce=int)
    notification_receiver = EmailField("Notification Email", validators=[OptionalValidator(), Length(max=models.User.email.type.length)])
    notification_comment = TextAreaField("Notification Comment", validators=[OptionalValidator(), Length(max=models.Comment.text.type.length)])

    def __init__(self, seq_request: Optional[models.SeqRequest] = None, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)
        self.__fill_form(seq_request)

    def __fill_form(self, seq_request: Optional[models.SeqRequest]):
        if seq_request is not None:
            self.notification_receiver.data = seq_request.requestor.email

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.response_type.data == -1:
            self.response_type.errors = ("Response is required.",)
            return False
        
        response_type = RequestResponse.get(self.response_type.data)
        
        if response_type != RequestResponse.ACCEPTED and not self.notification_comment.data:
            self.notification_comment.errors = ("Notification comment is required if request is not accepted.",)
            return False
        
        if self.notification_comment.data and not self.notification_receiver.data:
            self.notification_receiver.errors = ("Notification email is required if notification comment is provided.",)
            return False
        
        return True

    def process_request(self, **context) -> Response:
        seq_request = context["seq_request"]
        user = context["user"]

        if not self.validate():
            return self.make_response(**context)
        
        response_type = RequestResponse.get(self.response_type.data)

        if response_type == RequestResponse.ACCEPTED:
            seq_request = db.seq_requests.process(seq_request.id, SeqRequestStatus.ACCEPTED)
            flash("Request accepted!", "success")
        elif response_type == RequestResponse.REJECTED:
            seq_request = db.seq_requests.process(seq_request.id, SeqRequestStatus.REJECTED)
            flash("Request rejected!", "info")
        elif response_type == RequestResponse.PENDING_REVISION:
            seq_request = db.seq_requests.process(seq_request.id, SeqRequestStatus.DRAFT)
            flash("Request pending revision!", "info")
        else:
            raise exceptions.InternalServerErrorException()
        
        if self.notification_comment.data:
            _ = db.comments.create(
                text=f"Request {response_type.display_name}. Comment: {self.notification_comment.data}",
                author_id=user.id, seq_request_id=seq_request.id
            )
        else:
            _ = db.comments.create(
                text=f"Request {response_type.display_name}",
                author_id=user.id, seq_request_id=seq_request.id
            )

        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id))