import datetime as dt

from fastapi import Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, secrets, redis as rds
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..common import UserProfileMixin


class ActivationForm(UserProfileMixin, HTMXForm):
    """Reactivated account (link of the activation email): the user sets a password and, if a customer whose
    organization or PI is missing, fills them in. The link is single-use: setting the password invalidates it."""

    template_path = "forms/auth/activate.html"

    email = inputs.string.EmailInputField("Email", read_only=True, autocomplete="username")
    password = inputs.string.PasswordInputField("Password", min_length=8, autocomplete="new-password")
    confirm = inputs.string.PasswordInputField("Confirm Password", autocomplete="new-password")

    def __init__(self, token: str, user: models.User | None) -> None:
        super().__init__()
        self.token = token
        self.user = user
        self.post_url = responses.url_for("ActivationForm.Activate", token=token)
        self.init_profile_fields(user, token=token)

        if user is None:
            self.email.errors.append("Link expired or invalid.")
        else:
            self.email.data = user.email

    @property
    def asks_profile(self) -> bool:
        return self.user is not None and not self.user.is_insider and not self.user.profile_complete

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            token: str,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "ActivationForm":
            user = None
            if (user_id := secrets.verify_activation_token(token)) is not None:
                user = session.first(Q.user.select(id=user_id))
                if user is not None and (
                    user.role == C.UserRole.DEACTIVATED
                    or secrets.verify_activation_token(token, pw_set_datetime=user.pw_set_datetime) is None
                ):
                    user = None
            return ActivationForm(token=token, user=user)
        return dependency

    @htmx_route("GET", "/activate/{token}", name="Activate")
    def Render(cls) -> RouteFunc:
        def route(
            form: "ActivationForm" = Depends(ActivationForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/activate/{token}", name="Activate")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
            form: "ActivationForm" = Depends(ActivationForm.Validate()),
            r: rds.RedisClient = Depends(dependencies.redis),
            _ = Depends(dependencies.audit_log)
        ) -> Response:
            user = form.user
            if user is None:
                form.email.errors.append("Link expired or invalid.")
                raise exc.FormValidationException(form)

            if form.password.data != form.confirm.data:
                form.confirm.errors.append("Passwords must match.")
                raise exc.FormValidationException(form)

            if form.asks_profile:
                form.apply_profile(user, form.validate_profile(session, name=user.name, email=user.email, required=True))

            user.password = bcrypt.generate_password_hash(form.password.data)
            user.pw_set_datetime = dt.datetime.now(dt.timezone.utc)
            # Passkeys registered before the deactivation must be registered again, as after a password reset
            session.execute(Q.passkey.delete_all(user.id))
            r.delete(f"user:{user.id}")

            return responses.htmx_response(
                redirect=responses.url_for("login_page"),
                flash=responses.flash("Account activated, you can now log in.", "success"),
            )
        return route
