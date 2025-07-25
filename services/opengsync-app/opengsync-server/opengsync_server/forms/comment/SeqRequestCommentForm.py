from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response

from opengsync_db import models
from ... import db
from .CommentForm import CommentForm


class SeqRequestCommentForm(CommentForm):
    def __init__(self, seq_request: models.SeqRequest, formdata: Optional[dict] = None):
        CommentForm.__init__(self, formdata=formdata)
        self.seq_request = seq_request
        self._post_url = url_for("seq_requests_htmx.comment_form", seq_request_id=seq_request.id)

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        db.create_comment(
            text=self.comment.data,  # type: ignore
            author_id=user.id,
            seq_request_id=self.seq_request.id
        )

        flash("Comment added successfully.", "success")
        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id))
