from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import DateTimeLocalField, BooleanField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models, to_utc
from limbless_db.categories import EventType

from .. import db, logger  # noqa F401
from .HTMXFlaskForm import HTMXFlaskForm


class SubmitSeqRequestForm(HTMXFlaskForm):
    _template_path = "forms/seq_request/submit_request.html"
    _form_label = "submit_seq_request_form"

    sample_submission_time = DateTimeLocalField("Sample Submission Time", format="%Y-%m-%dT%H:%M", validators=[OptionalValidator()])
    samples_delivered_by_mail = BooleanField("Samples are Delivered by Mail", validators=[OptionalValidator()])

    def __init__(self, seq_request: models.SeqRequest, formdata=None):
        super().__init__(formdata=formdata)
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False

        if self.sample_submission_time.data is None and self.samples_delivered_by_mail.data is False:
            self.sample_submission_time.errors = ("Select sample submission time or delivery by mail.",)
            return False

        if self.sample_submission_time.data is not None:
            if self.sample_submission_time.data.weekday() > 4:
                self.sample_submission_time.errors = ("Sample submission time must be on a weekday.",)
                return False
            if self.sample_submission_time.data.time().hour < 9 or self.sample_submission_time.data.time().hour > 15:
                self.sample_submission_time.errors = ("Sample submission time must be between 9:00 and 15:00.",)
                return False

        return True

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.sample_submission_time.data is not None:
            if self.seq_request.sample_submission_event is None:
                self.seq_request.sample_submission_event = db.create_event(
                    title=f"Sample Submission: {self.seq_request.name}",
                    timestamp_utc=to_utc(self.sample_submission_time.data),
                    type=EventType.SAMPLE_SUBMISSION, user_id=user.id,
                )
            else:
                self.seq_request.sample_submission_event.timestamp_utc = to_utc(self.sample_submission_time.data)
            self.seq_request = db.update_seq_request(self.seq_request)

        self.seq_request = db.submit_seq_request(seq_request_id=self.seq_request.id)

        flash(f"Submitted sequencing request '{self.seq_request.name}'", "success")
        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id),)