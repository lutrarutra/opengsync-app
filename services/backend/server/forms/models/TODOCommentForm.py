from fastapi import Depends, Response

from opengsync_db import SyncSession, models, categories as C, queries as Q

from ...core import dependencies, responses, exceptions as exc
from ...components import inputs
from ..HTMXForm import FormFunc, HTMXForm, RouteFunc, htmx_route


class TODOCommentForm(HTMXForm):
    """Create or edit an insider-only TODO comment on a design resource."""

    template_path = "forms/todo_comment.html"

    text = inputs.string.TextAreaInputField("Note", max_length=2048)
    status_id = inputs.selectable.SelectableInputField(
        "Status",
        options=C.TaskStatus.as_selectable(),
        default=C.TaskStatus.IN_PROGRESS.id,
        required=False,
    )

    def __init__(
        self,
        todo_comment: models.TODOComment | None = None,
        flow_cell_design_id: int | None = None,
        pool_design_id: int | None = None,
    ) -> None:
        super().__init__()
        self.todo_comment = todo_comment
        self.flow_cell_design_id = flow_cell_design_id
        self.pool_design_id = pool_design_id

        if pool_design_id is not None and flow_cell_design_id is not None:
            raise exc.OpeNGSyncServerException(
                "Only one of pool_design_id or flow_cell_design_id can be set."
            )

        if todo_comment is not None:
            self.post_url = responses.url_for(
                "TODOCommentForm.Edit",
                todo_comment_id=todo_comment.id,
            )
        else:
            self.post_url = responses.url_for(
                "TODOCommentForm.Create",
                **self._resource_params(),
            )

    def _resource_params(self) -> dict[str, int]:
        if self.flow_cell_design_id is not None:
            return {"flow_cell_design_id": self.flow_cell_design_id}
        if self.pool_design_id is not None:
            return {"pool_design_id": self.pool_design_id}
        return {}

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            todo_comment_id: int | None = None,
            flow_cell_design_id: int | None = None,
            pool_design_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "TODOCommentForm":
            todo_comment = None
            if todo_comment_id is not None:
                todo_comment = session.first(Q.todo_comment.select(id=todo_comment_id))
                if todo_comment is None:
                    raise exc.NotFoundException("TODO Comment not found")
            return cls(
                todo_comment=todo_comment,
                flow_cell_design_id=flow_cell_design_id,
                pool_design_id=pool_design_id,
            )

        return dependency

    def populate_from_comment(self) -> None:
        if self.todo_comment is None:
            return
        self.text.data = self.todo_comment.text
        self.status_id.data = self.todo_comment.task_status_id

    @staticmethod
    def _set_comment_values(form: "TODOCommentForm") -> None:
        if form.todo_comment is None:
            raise exc.OpeNGSyncServerException("TODO comment must be provided for edit.")
        form.todo_comment.text = form.text.data
        form.todo_comment.task_status_id = form.status_id.data

    @htmx_route("GET", "/form", name="Render")
    def Render(cls) -> RouteFunc:
        def route(
            form: "TODOCommentForm" = Depends(TODOCommentForm.Init()),
            _=Depends(dependencies.require_insider),
        ):
            if form.todo_comment is not None:
                form.populate_from_comment()
            return form.make_response()
        return route

    @htmx_route("POST", "/form", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "TODOCommentForm" = Depends(TODOCommentForm.Validate()),
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> Response:
            if form.todo_comment is not None:
                raise exc.OpeNGSyncServerException("Use the edit route to update an existing TODO comment.")

            session.save(Q.todo_comment.create(
                text=form.text.data,
                status=C.TaskStatus.get(form.status_id.data) if form.status_id.data is not None else None,
                author=current_user,
                flow_cell_design_id=form.flow_cell_design_id,
                pool_design_id=form.pool_design_id,
            ), flush=True)
            return responses.htmx_response(
                redirect=responses.url_for("design"),
                flash=responses.flash("Comment added!", "success"),
            )
        return submit

    @htmx_route("POST", "/edit-form", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "TODOCommentForm" = Depends(TODOCommentForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.todo_comment is None:
                raise exc.OpeNGSyncServerException("TODO comment must be provided for edit.")
            TODOCommentForm._set_comment_values(form)
            session.save(form.todo_comment, flush=True)
            return responses.htmx_response(
                redirect=responses.url_for("design"),
                flash=responses.flash("Comment updated!", "success"),
            )
        return submit
