from typing import Optional, Any

from flask import Response, flash, url_for, abort
from flask_htmx import make_response
from wtforms import TextAreaField, EmailField, SelectField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from limbless_db import models
from limbless_db.core.categories import RequestResponse, SeqRequestStatus, HttpResponse
from .. import logger, db
from .HTMXFlaskForm import HTMXFlaskForm


class ProcessRequestForm(HTMXFlaskForm):
    _template_path = "forms/process_request.html"
    _form_label = "process_request_form"

    response_type = SelectField("Response", choices=[(-1, "")] + RequestResponse.as_selectable(), validators=[DataRequired()], default=None, coerce=int)
    notification_receiver = EmailField("Notification Email", validators=[OptionalValidator()])
    notification_comment = TextAreaField("Notification Comment", validators=[OptionalValidator()])

    def __init__(self, seq_request: Optional[models.SeqRequest] = None, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)
        self.__fill_form(seq_request)

    def __fill_form(self, seq_request: Optional[models.SeqRequest]):
        if seq_request is not None:
            self.notification_receiver.data = seq_request.requestor.email

    def validate(self) -> bool:
        if not super().validate():
            logger.debug(self.errors)
            return False
        
        if self.response_type.data == -1:
            self.response_type.errors = ("Response is required.",)
            return False
        
        response_type = RequestResponse.get(self.response_type.data)
        
        if response_type != RequestResponse.ACCEPTED and not self.notification_comment.data:
            self.notification_comment.errors = ("Notification comment is required if request is not accepted.",)
            return False
        
        return True

    def process_request(self, **context) -> Response:
        seq_request = context["seq_request"]

        if not self.validate():
            return self.make_response(**context)
        
        response_type = RequestResponse.get(self.response_type.data)

        if response_type == RequestResponse.ACCEPTED:
            seq_request.status_id = SeqRequestStatus.PREPARATION.value.id
            seq_request = db.update_seq_request(seq_request)
            flash("Request accepted!", "success")
        elif response_type == RequestResponse.REJECTED:
            seq_request.status_id = SeqRequestStatus.FAILED.value.id
            seq_request = db.update_seq_request(seq_request)
            flash("Request rejected!", "success")
        elif response_type == RequestResponse.PENDING_REVISION:
            seq_request.status_id = SeqRequestStatus.DRAFT.value.id
            seq_request = db.update_seq_request(seq_request)
            flash("Request pending revision!", "success")
        else:
            return abort(HttpResponse.INTERNAL_SERVER_ERROR.value.id)

        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))