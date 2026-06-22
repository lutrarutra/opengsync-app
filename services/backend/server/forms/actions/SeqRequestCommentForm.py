from fastapi import Request

from opengsync_db import models

from ...components import inputs
from ..HTMXForm import HTMXForm


class SeqRequestCommentForm(HTMXForm):
    template_path = "components/popups/comment-form.html"

    comment = inputs.string.TextAreaInputField(
        "Comment", required=True, max_length=4096
    )

    def __init__(self, request: Request, seq_request: models.SeqRequest):
        super().__init__(request)
        self.seq_request = seq_request
