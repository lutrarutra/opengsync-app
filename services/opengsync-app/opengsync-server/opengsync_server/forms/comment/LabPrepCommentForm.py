from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response

from opengsync_db import models
from ... import db
from .CommentForm import CommentForm


class LabPrepCommentForm(CommentForm):
    _template_path = "components/popups/comment-form.html"
    _template_label = "comment_form"

    def __init__(self, lab_prep: models.LabPrep, formdata: Optional[dict] = None):
        CommentForm.__init__(self, formdata=formdata)
        self.lab_prep = lab_prep
        self._post_url = url_for("lab_preps_htmx.comment_form", lab_prep_id=lab_prep.id)

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        db.comments.create((
            text=self.comment.data,  # type: ignore
            author_id=user.id,
            lab_prep_id=self.lab_prep.id
        )

        flash("Comment added successfully.", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id, tab="comments-tab"))
