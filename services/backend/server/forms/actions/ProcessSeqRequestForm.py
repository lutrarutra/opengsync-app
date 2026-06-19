from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, AsyncSession, categories as C, models, actions
from opengsync_db.categories import UserRole

from ...core import responses, secrets, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm

class ProcessSeqRequestForm(HTMXForm):
    template_path = "forms/process_request.html"

    response_type = inputs.selectable.SelectableInputField("Response", C.RequestResponse.as_selectable())
    notification_receiver = inputs.string.EmailInputField("Notification Email", max_length=255, required=False)
    notification_comment = inputs.string.TextAreaInputField("Notification Comment", max_length=4096, required=False)
    assign_seq_request_to_me = inputs.boolean.BooleanInputField("Assign request to me", default=True)

    def __init__(self, request: Request, seq_request: models.SeqRequest):
        super().__init__(request)
        self.seq_request = seq_request

    async def prepare(self):
        self.notification_receiver.data = self.seq_request.contact_person.email or self.seq_request.requestor.email

    @staticmethod
    async def process_request(
        request: Request,
        seq_request_id: int,
        current_user: models.User = Depends(dependencies.require_insider),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        seq_request = await session.get_one(Q.seq_request.select(seq_request_id))
        form = ProcessSeqRequestForm(request, seq_request=seq_request)
        await form.validate()

        response_type = C.RequestResponse.get(form.response_type.data)

        flash = None
        if response_type == C.RequestResponse.ACCEPTED:
            seq_request = actions.process_seq_request(
                session=session.sync_session, seq_request=form.seq_request, status=C.SeqRequestStatus.ACCEPTED
            )
            flash = responses.flash("Request accepted!", "success")
        elif response_type == C.RequestResponse.REJECTED:
            seq_request = actions.process_seq_request(
                session=session.sync_session, seq_request=form.seq_request, status=C.SeqRequestStatus.REJECTED
            )
            flash = responses.flash("Request rejected!", "info")
        elif response_type == C.RequestResponse.PENDING_REVISION:
            seq_request = actions.process_seq_request(
                session=session.sync_session, seq_request=form.seq_request, status=C.SeqRequestStatus.DRAFT
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
            if seq_request not in current_user.assigned_seq_requests:
                current_user.assigned_seq_requests.append(seq_request)

        # TODO: send notification email if notification_comment is provided

        return await responses.htmx_response(
            redirect=responses.url_for("seq_request_page", seq_request_id=seq_request.id),
            flash=flash
        )
