from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import TextAreaField, SelectField
from wtforms.validators import DataRequired, Length

from opengsync_db import models, categories as cats

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm


class TODOCommentForm(HTMXFlaskForm):
    _template_path = "forms/todo_comment.html"

    text = TextAreaField("Note", validators=[DataRequired(), Length(min=1, max=2048)])
    status_id = SelectField("Status", validators=[DataRequired()], choices=[(-1, "-")] + cats.TaskStatus.as_selectable(), default=cats.TaskStatus.IN_PROGRESS.id, coerce=int)

    def __init__(
        self,
        todo_comment: models.TODOComment | None,
        flow_cell_design: models.FlowCellDesign | None,
        pool_design: models.PoolDesign | None,
        formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        self.pool_design = pool_design
        self.flow_cell_design = flow_cell_design
        self.todo_comment = todo_comment
        if pool_design is not None and flow_cell_design is not None:
            raise ValueError("Only one of pool_design or flow_cell_design can be set")
        self._context["pool_design"] = pool_design
        self._context["flow_cell_design"] = flow_cell_design
        self._context["todo_comment"] = todo_comment

        url_context = {}
        if flow_cell_design is not None:
            url_context["flow_cell_design_id"] = flow_cell_design.id
        if pool_design is not None:
            url_context["pool_design_id"] = pool_design.id
        if todo_comment is not None:
            url_context["todo_comment_id"] = todo_comment.id
        self.post_url = url_for('design_htmx.comment_form', **url_context)

    def prepare(self) -> None:
        if self.todo_comment is None:
            return
        
        self.text.data = self.todo_comment.text
        

    def process_request(self, current_user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        new_todo_comment = models.TODOComment(
            text=self.text.data,  # type: ignore
            task_status_id=self.status_id.data if self.status_id.data != -1 else None,
            pool_design_id=self.pool_design.id if self.pool_design else None,
            flow_cell_design_id=self.flow_cell_design.id if self.flow_cell_design else None,
            author=current_user,
        )
        db.session.add(new_todo_comment)
        db.flush()
        flash("Comment Added!", "success")
        return make_response(redirect=url_for("design_page.design"))


        


