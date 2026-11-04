from fastapi import Depends
from fastapi.responses import Response
from loguru import logger
from sqlalchemy import orm

from opengsync_db import queries as Q, SyncSession, categories as C, models, actions

from ...core import responses, dependencies, exceptions as exc
from ...core.mailer import Mailer
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class ProcessSeqRequestAction(HTMXForm):
    template_path = "actions/process-request.html"

    response_type = inputs.selectable.SelectableInputField("Response", C.RequestResponse.as_selectable())
    notification_receiver = inputs.string.EmailInputField("Notification Email", max_length=255, required=False)
    notification_comment = inputs.string.TextAreaInputField("Notification Comment", max_length=4096, required=False)
    notify_customer = inputs.boolean.BooleanInputField("Send notification email")
    assign_seq_request_to_me = inputs.boolean.BooleanInputField("Assign request to me", default=True)

    def __init__(self, seq_request: models.SeqRequest, submitter: models.User | None):
        super().__init__()
        self.seq_request = seq_request
        self.submitter = submitter
        self._context["seq_request"] = seq_request
        self._context["submitter"] = submitter
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
            submitter = session.first(Q.seq_request.submitted_by(seq_request.id))
            return ProcessSeqRequestAction(seq_request=seq_request, submitter=submitter)
        return form
    
    @property
    def customer_submitted(self) -> bool:
        return self.submitter is not None and not self.submitter.is_insider

    def send_notification(self, mailer: Mailer, response_type: C.RequestResponse) -> responses.FlashMessage | None:
        """Returns a warning flash when the email could not be sent; the request is processed regardless."""
        receiver = self.notification_receiver.data
        try:
            mailer.send_seq_request_processed(
                receiver, self.seq_request, response_type, comment=self.notification_comment.data or None,
            )
        except Exception as e:
            logger.error(f"Failed to send request notification to '{receiver}': {e}")
            return responses.flash(f"Request processed, but the notification email to {receiver} could not be sent.", "warning")
        return None

    @htmx_route("GET", "/{seq_request_id}/process-request")
    def Begin(cls) -> RouteFunc:
        def route(
            form: ProcessSeqRequestAction = Depends(ProcessSeqRequestAction.Init()),
            _ = Depends(dependencies.require_insider),
        ):
            form.notification_receiver.data = form.seq_request.contact_person.email or form.seq_request.requestor.email
            # notify by default only when a customer submitted the request themselves:
            # requests that insiders fill in and submit on a customer's behalf stay silent
            form.notify_customer.data = form.customer_submitted
            return form.make_response()
        return route

    @htmx_route("POST", "/{seq_request_id}/process-request")
    def Submit(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_insider),
            form: ProcessSeqRequestAction = Depends(ProcessSeqRequestAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            mailer: Mailer = Depends(dependencies.mail_client),
        ) -> Response:
            response_type = C.RequestResponse.get(form.response_type.data)

            if response_type != C.RequestResponse.ACCEPTED and not (form.notification_comment.data or "").strip():
                form.notification_comment.errors.append("A comment is required if the request is not accepted.")
                raise exc.FormValidationException(form)
            if form.notify_customer.data and not form.notification_receiver.data:
                form.notification_receiver.errors.append("Notification email is required to notify the customer.")
                raise exc.FormValidationException(form)

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

            if form.notify_customer.data:
                session.flush()
                flash = form.send_notification(mailer, response_type) or flash

            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=flash
            )
        return route

