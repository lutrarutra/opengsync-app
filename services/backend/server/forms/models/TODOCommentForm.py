

from sqlalchemy import select as sa_select

from fastapi import Request, Query, Response, Depends

from opengsync_db import models, SyncSession, categories as C, queries as Q

from ...core import dependencies, responses, exceptions as exc
from ..HTMXForm import HTMXForm
from ...components import inputs


class TODOCommentForm(HTMXForm):
    template_path = "forms/todo_comment.html"

    text = inputs.string.TextAreaInputField("Note", max_length=2048)
    status_id = inputs.selectable.SelectableInputField(
        "Status",
        options=[(-1, "-")] + C.TaskStatus.as_selectable(),
        default=C.TaskStatus.IN_PROGRESS.id,
        required=False,
    )

    def __init__(
        self,
        request: Request,
        *,
        todo_comment: models.TODOComment | None = None,
        flow_cell_design_id: int | None = None,
        pool_design_id: int | None = None,
    ):
        super().__init__(request)
        self.todo_comment = todo_comment
        self.flow_cell_design_id = flow_cell_design_id
        self.pool_design_id = pool_design_id

        if pool_design_id is not None and flow_cell_design_id is not None:
            raise ValueError("Only one of pool_design_id or flow_cell_design_id can be set")

        self._context["todo_comment"] = todo_comment
        self._context["flow_cell_design_id"] = flow_cell_design_id
        self._context["pool_design_id"] = pool_design_id

        # Build post_url for the template — points to the comments router
        url_kwargs: dict[str, int] = {}
        if flow_cell_design_id is not None:
            url_kwargs["flow_cell_design_id"] = flow_cell_design_id
        if pool_design_id is not None:
            url_kwargs["pool_design_id"] = pool_design_id
        if todo_comment is not None:
            url_kwargs["todo_comment_id"] = todo_comment.id

        self.post_url = responses.url_for("comment_form", **url_kwargs)

    def prepare(self) -> None:
        if self.todo_comment is None:
            return
        self.text.data = self.todo_comment.text

    @staticmethod
    def check_permissions(current_user: models.User) -> None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException(
                "You do not have permission to manage TODO comments on design resources."
            )

    @staticmethod
    def submit_form(
        request: Request,
        current_user: models.User = Depends(dependencies.require_insider),
        session: SyncSession = Depends(dependencies.db_session),
        todo_comment_id: int | None = Query(None),
        flow_cell_design_id: int | None = Query(None),
        pool_design_id: int | None = Query(None),
    ) -> Response:
        """Process the TODO comment form submission (create)."""

        todo_comment: models.TODOComment | None = None
        if todo_comment_id is not None:
            result = session.execute(
                sa_select(models.TODOComment).where(models.TODOComment.id == todo_comment_id)
            )
            todo_comment = result.scalar_one_or_none()
            if todo_comment is None:
                raise exc.ItemNotFoundException("TODO Comment not found")

        form = TODOCommentForm(
            request,
            todo_comment=todo_comment,
            flow_cell_design_id=flow_cell_design_id,
            pool_design_id=pool_design_id,
        )
        form.validate()

        new_comment = models.TODOComment(
            text=form.text.data,
            task_status_id=(
                form.status_id.data if form.status_id.data != -1 else None
            ),
            flow_cell_design_id=flow_cell_design_id,
            pool_design_id=pool_design_id,
            author=current_user,
        )
        session.add(new_comment)

        return responses.htmx_response(
            redirect=responses.url_for("design"),
            flash=responses.flash("Comment added!", "success"),
        )