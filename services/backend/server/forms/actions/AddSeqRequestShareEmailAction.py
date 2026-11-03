from typing import Literal

from fastapi import Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C
from opengsync_db.transitions import run_operation, create as create_ops

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm

ShareEmailContext = Literal["share", "submit", "review"]
"""Where the list is shown: the Share tab, the submit checklist or the (insider) review checklist."""


class AddSeqRequestShareEmailAction(HTMXForm):
    """Inline list of a seq request's data share emails with a row to add one.

    Adding needs READ at any status (customers may add recipients after submission),
    removing needs WRITE (owners only while DRAFT) and at least one email has to remain.
    In the review checklist everything requires INSIDER.
    """
    template_path = "components/seq_request-share-emails.html"

    email = inputs.string.EmailInputField("Email", required=True, max_length=128, placeholder="name@example.com")

    def __init__(self, seq_request: models.SeqRequest, context: ShareEmailContext, access_level: C.AccessLevel):
        super().__init__()
        if context == "review" and access_level < C.AccessLevel.INSIDER:
            raise exc.NoPermissionsException()
        self.seq_request = seq_request
        self.share_context = context
        self.access_level = access_level
        self.email.id = f"share-email-{context}"
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", seq_request_id=seq_request.id).include_query_params(context=context)
        self.get_url = responses.url_for(f"{self.__class__.__name__}.Begin", seq_request_id=seq_request.id).include_query_params(context=context)

    def prepare_context(self) -> None:
        super().prepare_context()
        if len(self.seq_request.delivery_email_links) <= 1:
            remove_disabled_reason = "At least one email is required. Add another email to remove this one."
        elif self.access_level < C.AccessLevel.WRITE:
            remove_disabled_reason = "Only insiders can remove emails from a submitted request."
        else:
            remove_disabled_reason = None
        self._context.update(
            seq_request=self.seq_request,
            context=self.share_context,
            post_url=self.post_url,
            get_url=self.get_url,
            can_add=self.access_level >= C.AccessLevel.READ,
            can_remove=remove_disabled_reason is None,
            remove_disabled_reason=remove_disabled_reason,
        )

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            seq_request_id: int,
            context: ShareEmailContext = Query("share"),
            session: SyncSession = Depends(dependencies.db_session),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
        ):
            seq_request = session.get_one(Q.seq_request.select(id=seq_request_id), options=[orm.selectinload(models.SeqRequest.delivery_email_links)])
            return AddSeqRequestShareEmailAction(seq_request=seq_request, context=context, access_level=access_level)
        return form

    def changed_response(self, flash: responses.FlashMessage):
        """Re-render with an empty input, tell the other lists on the page to refresh and update the badges."""
        fresh = AddSeqRequestShareEmailAction(seq_request=self.seq_request, context=self.share_context, access_level=self.access_level)
        return fresh.make_response(
            flash=flash,
            trigger={"shareEmailsChanged": {"context": self.share_context}},
            changed=True,
        )

    @htmx_route("GET", "/{seq_request_id}/share-email")
    def Begin(cls) -> RouteFunc:
        def route(form: AddSeqRequestShareEmailAction = Depends(AddSeqRequestShareEmailAction.Init())):
            return form.make_response()
        return route

    @htmx_route("POST", "/{seq_request_id}/share-email")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            form: "AddSeqRequestShareEmailAction" = Depends(AddSeqRequestShareEmailAction.Validate()),
        ):
            email = form.email.data.strip()
            if email in [link.email for link in form.seq_request.delivery_email_links]:
                form.email.errors.append("This email address is already in the list.")
                raise exc.FormValidationException(form)

            with run_operation(session, create_ops.ADD_SHARE_EMAIL, subject=form.seq_request):
                form.seq_request.delivery_email_links.append(
                    models.links.SeqRequestDeliveryEmailLink(email=email, status=C.DeliveryStatus.PENDING)
                )
                session.save(form.seq_request)

            return form.changed_response(responses.flash(f"Email {email} added successfully.", "success"))
        return route

    @htmx_route("DELETE", "/{seq_request_id}/share-email/{email}")
    def Remove(cls) -> RouteFunc:
        def route(
            email: str,
            session: SyncSession = Depends(dependencies.db_session),
            form: "AddSeqRequestShareEmailAction" = Depends(AddSeqRequestShareEmailAction.Init()),
        ):
            if form.access_level < C.AccessLevel.WRITE or len(form.seq_request.delivery_email_links) <= 1:
                raise exc.NoPermissionsException()

            if (link := next((link for link in form.seq_request.delivery_email_links if link.email == email), None)) is None:
                raise exc.NotFoundException()

            form.seq_request.delivery_email_links.remove(link)
            session.delete(link)
            session.flush()

            return form.changed_response(responses.flash(f"Email {email} removed.", "success"))
        return route
