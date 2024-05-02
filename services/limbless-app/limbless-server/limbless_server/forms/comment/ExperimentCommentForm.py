from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response

from limbless_db import models
from ... import db
from .CommentForm import CommentForm


class ExperimentCommentForm(CommentForm):
    _template_path = "components/popups/comment-form.html"
    _template_label = "comment_form"

    def __init__(self, experiment_id: int, formdata: Optional[dict] = None):
        CommentForm.__init__(self, formdata=formdata)
        self._post_url = url_for("experiments_htmx.add_comment", experiment_id=experiment_id)

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        user: models.User = context["user"]
        experiment: models.Experiment = context["experiment"]
        
        comment = db.create_comment(
            text=self.comment.data,  # type: ignore
            author_id=user.id,
        )

        db.add_experiment_comment(comment_id=comment.id, experiment_id=experiment.id)
        flash("Comment added successfully.", "success")
        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))
