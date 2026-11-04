from fastapi import Depends
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, responses, secrets
from ...core.mailer import Mailer
from ..auth.RegisterForm import email_domain_allowed
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class AddUserToGroupAction(HTMXForm):
    template_path = "actions/add-user-to-group.html"

    email = inputs.string.EmailInputField("Email", required=True, max_length=255)
    affiliation_type = inputs.selectable.SelectableInputField(
        "Affiliation Type",
        C.AffiliationType.as_selectable_no_owner(),
        default=C.AffiliationType.MEMBER.id,
    )

    def __init__(self, group: models.Group):
        super().__init__()
        self.group = group
        self._context["group"] = group
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", group_id=group.id)

    def invite(self, email: str, inviter: models.User, mailer: Mailer):
        """Someone without an account: send a registration link that joins the group on completion."""
        if not inviter.is_insider and not email_domain_allowed(email):
            self.email.errors.append("No account with this email, and its domain cannot register. Please contact us.")
            raise exc.FormValidationException(self)
        token = secrets.generate_registration_token(
            email=email, role=C.UserRole.CLIENT, group_id=self.group.id,
            affiliation_type=C.AffiliationType.get(self.affiliation_type.data),
        )
        try:
            mailer.send_registration(email, responses.external_url_for("complete_registration_page", token=token))
        except Exception as e:
            logger.error(f"Failed to send group invitation to '{email}': {e}")
            self.email.errors.append("Failed to send the invitation email. Please contact us.")
            raise exc.FormValidationException(self)
        return responses.htmx_response(
            redirect=responses.url_for("group_page", group_id=self.group.id),
            flash=responses.flash(f"Invitation sent to {email}. They join the group once they complete the registration.", "success"),
        )

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            group_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ):
            group = session.get_one(Q.group.select(id=group_id))
            return AddUserToGroupAction(group=group)
        return form

    @htmx_route("GET", "/{group_id}/add-user")
    def Begin(cls) -> RouteFunc:
        def route(
            form: AddUserToGroupAction = Depends(AddUserToGroupAction.Init()),
            access_level: C.AccessLevel = Depends(dependencies.group_permissions),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            return form.make_response()
        return route

    @htmx_route("POST", "/{group_id}/add-user")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            access_level: C.AccessLevel = Depends(dependencies.group_permissions),
            current_user: models.User = Depends(dependencies.require_user),
            mailer: Mailer = Depends(dependencies.mail_client),
            form: "AddUserToGroupAction" = Depends(AddUserToGroupAction.Validate()),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()

            if C.AffiliationType.get(form.affiliation_type.data) == C.AffiliationType.OWNER:
                form.affiliation_type.errors.append("Owner affiliation type is not allowed.")
                raise exc.FormValidationException(form)

            email = form.email.data.strip()
            if (user := session.first(Q.user.select(email=email))) is None:
                return form.invite(email, current_user, mailer)

            if session.first(Q.affiliation.select(user_id=user.id, group_id=form.group.id)) is not None:
                form.email.errors.append("User is already in this group.")
                raise exc.FormValidationException(form)

            session.save(Q.affiliation.create(
                user=user,
                group=form.group,
                type=C.AffiliationType.get(form.affiliation_type.data),
            ))

            return responses.htmx_response(
                redirect=responses.url_for("group_page", group_id=form.group.id),
                flash=responses.flash("User added to group.", "success"),
            )
        return route