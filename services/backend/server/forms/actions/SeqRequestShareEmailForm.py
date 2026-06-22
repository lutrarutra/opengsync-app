from fastapi import Request

from opengsync_db import models

from ...components import inputs
from ..HTMXForm import HTMXForm


class SeqRequestShareEmailForm(HTMXForm):
    template_path = "components/popups/seq_request_share_email_form.html"

    email = inputs.string.EmailInputField("Email", required=True, max_length=255)

    def __init__(self, request: Request, seq_request: models.SeqRequest):
        super().__init__(request)
        self.seq_request = seq_request
