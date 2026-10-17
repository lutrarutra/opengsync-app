from fastapi import Depends
from fastapi.responses import Response
from sqlalchemy import orm

from opengsync_db import queries as Q, SyncSession, categories as C, models, actions

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class ProcessSeqRequestAction(HTMXForm):
    template_path = "actions/process-request.html"

    response_type = inputs.selectable.SelectableInputField("Response", C.RequestResponse.as_selectable())
    notification_receiver = inputs.string.EmailInputField("Notification Email", max_length=255, required=False)
    notification_comment = inputs.string.TextAreaInputField("Notification Comment", max_length=4096, required=False)
    assign_seq_request_to_me = inputs.boolean.BooleanInputField("Assign request to me", default=True)

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
            seq_request = session.get_one(Q.seq_request.select(id=seq_request_id), options=[
                orm.selectinload(models.SeqRequest.samples),
                orm.selectinload(models.SeqRequest.libraries),
                orm.selectinload(models.SeqRequest.pools),
                orm.selectinload(models.SeqRequest.comments),
                orm.selectinload(models.SeqRequest.contact_person),
            ])
            return ProcessSeqRequestAction(seq_request=seq_request)
        return form
    
    @htmx_route("GET", "/{seq_request_id}/process-request")
    def Begin(cls) -> RouteFunc:
        def route(
            form: ProcessSeqRequestAction = Depends(ProcessSeqRequestAction.Init()),
            _ = Depends(dependencies.require_insider),
        ):
            form.notification_receiver.data = form.seq_request.contact_person.email or form.seq_request.requestor.email
            return form.make_response()
        return route

    @htmx_route("POST", "/{seq_request_id}/process-request")
    def Submit(cls) -> RouteFunc:
        def route(
            form: ProcessSeqRequestAction = Depends(ProcessSeqRequestAction.Validate()),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            response_type = C.RequestResponse.get(form.response_type.data)

            flash = None
            if response_type == C.RequestResponse.ACCEPTED:
                seq_request = actions.process_seq_request(
                    session=session, seq_request=form.seq_request, status=C.SeqRequestStatus.ACCEPTED
                )
                flash = responses.flash("Request accepted!", "success")
            elif response_type == C.RequestResponse.REJECTED:
                seq_request = actions.process_seq_request(
                    session=session, seq_request=form.seq_request, status=C.SeqRequestStatus.REJECTED
                )
                flash = responses.flash("Request rejected!", "info")
            elif response_type == C.RequestResponse.PENDING_REVISION:
                seq_request = actions.process_seq_request(
                    session=session, seq_request=form.seq_request, status=C.SeqRequestStatus.DRAFT
                )
                flash = responses.flash("Request marked as pending revision.", "info")
            else:
                raise exc.OpeNGSyncServerException()
            
            if form.notification_comment.data:
                form.seq_request.comments.append(Q.comment.create(
                    text=f"Request {response_type.display_name}. Comment: {form.notification_comment.data}",
                    author=current_user,
                ))
            else:
                form.seq_request.comments.append(Q.comment.create(
                    text=f"Request {response_type.display_name}",
                    author=current_user
                ))

            if form.assign_seq_request_to_me.data:
                session.refresh(current_user, attribute_names=["assigned_seq_requests"])
                if seq_request not in current_user.assigned_seq_requests:
                    current_user.assigned_seq_requests.append(seq_request)

            # TODO: send notification email if notification_comment is provided

            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=flash
            )
        return route

