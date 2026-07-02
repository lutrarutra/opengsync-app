from fastapi import Request

from opengsync_db import models

from ...core import config
from ...components import inputs
from ..HTMXForm import HTMXForm


class SubmitSeqRequestForm(HTMXForm):
    template_path = "forms/seq_request/submit_request.html"

    sample_submission_time = inputs.string.StringInputField(
        "Sample Submission Time", required=False
    )
    samples_delivered_by_mail = inputs.boolean.CheckboxInputField(
        "Samples are Delivered by Mail"
    )
    custom_sample_submission_time = inputs.boolean.CheckboxInputField(
        "We have agreed to a time that is outside the available submission windows."
    )
    comment = inputs.string.TextAreaInputField(
        "Additional Comment for Submission", required=False, max_length=4096
    )

    def __init__(self, request: Request, seq_request: models.SeqRequest):
        super().__init__(request)
        self.seq_request = seq_request

    def prepare(self) -> None:
        pass

    def get_context(self) -> dict:
        context = super().get_context()
        context["seq_request"] = self.seq_request
        context["sample_submission_windows"] = (
            config.settings.app_config.sample_submission_windows
        )
        return context
