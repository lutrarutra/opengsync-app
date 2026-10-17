from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...components import inputs
from ...core import dependencies, exceptions as exc, responses
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class AddSeqRequestAssigneeAction(HTMXForm):
    template_path = "actions/add-seq_request-assignee.html"

    user_id = inputs.searchable.SearchableInputField("Select User", route="search_users", required=True)

    def __init__(self, seq_request: models.SeqRequest):
        super().__init__()
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", seq_request_id=seq_request.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            seq_request_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ):
            seq_request = session.get_one(Q.seq_request.select(id=seq_request_id), options=[orm.selectinload(models.SeqRequest.assignees)])
            return AddSeqRequestAssigneeAction(seq_request=seq_request)
        return form

    @htmx_route("GET", "/{seq_request_id}/add-assignee")
    def Begin(cls) -> RouteFunc:
        def route(
            form: AddSeqRequestAssigneeAction = Depends(AddSeqRequestAssigneeAction.Init()),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            if current_user not in form.seq_request.assignees:
                form.user_id.data = current_user.id
            return form.make_response()
        return route
            

    @htmx_route("POST", "/{seq_request_id}/add-assignee")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            form: "AddSeqRequestAssigneeAction" = Depends(AddSeqRequestAssigneeAction.Validate()),
            _ = Depends(dependencies.require_insider),
        ):
            assignee = session.get_one(Q.user.select(id=int(form.user_id.data)))

            if not assignee.is_insider:
                form.user_id.errors.append("Only insider users can be assigned to requests.")
                raise exc.FormValidationException(form)

            if assignee in form.seq_request.assignees:
                form.user_id.errors.append(f"User {assignee.name} is already an assignee in this request.")
                raise exc.FormValidationException(form)

            form.seq_request.assignees.append(assignee)
            session.save(form.seq_request)

            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=form.seq_request.id).include_query_params(tab="request-assignees-tab"),
                flash=responses.flash("Assignee added successfully.", "success"),
            )
        return route
