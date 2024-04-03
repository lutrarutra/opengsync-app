from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response

from limbless_db import models
from ... import db
from .CommentForm import CommentForm


class SeqRequestCommentForm(CommentForm):
    def __init__(self, seq_request_id: int, formdata: Optional[dict] = None):
        CommentForm.__init__(self, formdata=formdata)
        self._post_url = url_for("seq_requests_htmx.add_comment", seq_request_id=seq_request_id)

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        user: models.User = context["user"]
        seq_request: models.Experiment = context["seq_request"]
        
        comment = db.create_comment(
            text=self.comment.data,  # type: ignore
            author_id=user.id,
        )

        db.add_seq_request_comment(comment_id=comment.id, seq_request_id=seq_request.id)
        flash("Comment added successfully.", "success")
        return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id))
