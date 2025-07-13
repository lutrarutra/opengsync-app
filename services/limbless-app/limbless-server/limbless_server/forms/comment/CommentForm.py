from flask import Response
from wtforms import TextAreaField
from wtforms.validators import DataRequired, Length

from opengsync_db import models
from ..HTMXFlaskForm import HTMXFlaskForm


class CommentForm(HTMXFlaskForm):
    _template_path = "components/popups/comment-form.html"
    _form_label = "comment_form"

    comment = TextAreaField("Comment", validators=[DataRequired(), Length(max=models.Comment.text.type.length)])

    def validate(self) -> bool:
        return super().validate()
    
    def process_request(self, **context) -> Response:
        raise NotImplementedError("Subclasses must implement this method.")