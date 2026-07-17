from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class AddSeqRequestShareEmailAction(HTMXForm):
    template_path = "actions/add-seq_request-share-email.html"

    email = inputs.string.EmailInputField("Email", required=True, max_length=255)

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
            seq_request = session.get_one(Q.seq_request.select(id=seq_request_id), options=[orm.selectinload(models.SeqRequest.delivery_email_links)])
            return AddSeqRequestShareEmailAction(seq_request=seq_request)
        return form
    
    @htmx_route("GET", "/{seq_request_id}/share-email")
    def Begin(cls) -> RouteFunc:
        def route(
            form: AddSeqRequestShareEmailAction = Depends(AddSeqRequestShareEmailAction.Init()),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            return form.make_response()
        return route
    
    @htmx_route("POST", "/{seq_request_id}/share-email")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            form: "AddSeqRequestShareEmailAction" = Depends(AddSeqRequestShareEmailAction.Validate()),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            
            email = form.email.data.strip()
            if email in [link.email for link in form.seq_request.delivery_email_links]:
                form.email.errors.append("This email address is already in the list.")
                raise exc.FormValidationException(form)

            form.seq_request.delivery_email_links.append(
                models.links.SeqRequestDeliveryEmailLink(email=email)
            )
            session.save(form.seq_request)

            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=form.seq_request.id).include_query_params(tab="request-shares-tab"),
                flash=responses.flash(f"Email {email} added successfully.", "success"),
            )
        return route
