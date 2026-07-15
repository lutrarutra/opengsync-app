from fastapi import Request, Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...components import inputs
from ...core import dependencies, exceptions as exc, responses
from ..HTMXForm import HTMXForm


class AddSeqRequestAssigneeForm(HTMXForm):
    template_path = "forms/add-seq_request-assignee.html"

    user_id = inputs.searchable.SearchableInputField("Select User", route="search_users", required=True)

    def __init__(
        self,
        request: Request,
        seq_request: models.SeqRequest,
        current_user: models.User,
    ):
        super().__init__(request)
        self.seq_request = seq_request
        self.current_user = current_user
        self._context["seq_request"] = seq_request

    def prepare(self) -> None:
        if self.current_user not in self.seq_request.assignees:
            self.user_id.data = str(self.current_user.id)

    @staticmethod
    def add_assignee(
        seq_request_id: int,
        request: Request,
        session: SyncSession = Depends(dependencies.db_session),
        current_user: models.User = Depends(dependencies.require_insider),
    ):
        seq_request = session.get_one(
            Q.seq_request.select(id=seq_request_id),
            options=[orm.selectinload(models.SeqRequest.assignees)],
        )
        form = AddSeqRequestAssigneeForm(request, seq_request=seq_request, current_user=current_user)
        form.validate()

        assignee = session.get_one(Q.user.select(id=int(form.user_id.data)))

        if not assignee.is_insider:
            form.user_id.errors.append("Only insider users can be assigned to requests.")
            raise exc.FormValidationException(form)

        if assignee in seq_request.assignees:
            form.user_id.errors.append(
                f"User {assignee.name} is already an assignee in this request."
            )
            raise exc.FormValidationException(form)

        seq_request.assignees.append(assignee)
        session.save(seq_request)

        return responses.htmx_response(
            redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id).include_query_params(tab="request-assignees-tab"),
            flash=responses.flash("Assignee added successfully.", "success"),
        )
