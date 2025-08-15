from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response

from opengsync_db import models
from ... import db
from .CommentForm import CommentForm


class ExperimentCommentForm(CommentForm):
    _template_path = "components/popups/comment-form.html"
    _template_label = "comment_form"

    def __init__(self, experiment: models.Experiment, formdata: Optional[dict] = None):
        CommentForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._post_url = url_for("experiments_htmx.comment_form", experiment_id=experiment.id)

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        db.comments.create(
            text=self.comment.data,  # type: ignore
            author_id=user.id,
            experiment_id=self.experiment.id
        )

        flash("Comment added successfully.", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id, tab="experiment-comments-tab"))
