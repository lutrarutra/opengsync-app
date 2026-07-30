from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models

from ...core import responses, dependencies, exceptions as exc, secrets
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class ResetPasswordForm(HTMXForm):
    template_path = "forms/auth/reset_password.html"

    email = inputs.string.EmailInputField("Email", read_only=True)
    password = inputs.string.PasswordInputField("Password", min_length=8)
    confirm = inputs.string.PasswordInputField("Confirm Password")

    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token
        self.post_url = responses.url_for("ResetPasswordForm.ResetPassword", token=token)

        user_id = secrets.verify_password_reset_token(token)
        if user_id is None:
            self.email.errors.append("Token expired or invalid.")
            return

        self.user_id = user_id

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(token: str) -> "ResetPasswordForm":
            return ResetPasswordForm(token=token)
        return dependency

    @htmx_route("GET", "/reset-password/{token}", name="ResetPassword")
    def Render(cls) -> RouteFunc:
        def route(
            form: "ResetPasswordForm" = Depends(ResetPasswordForm.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            if form.user_id is None:
                return form.make_response()

            user = session.get_one(Q.user.select(id=form.user_id))
            form.email.data = user.email
            return form.make_response()
        return route

    @htmx_route("POST", "/reset-password/{token}", name="ResetPassword")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
            form: "ResetPasswordForm" = Depends(ResetPasswordForm.Validate()),
            _ = Depends(dependencies.audit_log)
        ) -> Response:
            user_id = secrets.verify_password_reset_token(form.token)
            if user_id is None:
                form.email.errors.append("Token expired or invalid.")
                raise exc.FormValidationException(form)

            if form.password.data != form.confirm.data:
                form.confirm.errors.append("Passwords must match.")
                raise exc.FormValidationException(form)

            user = session.get_one(Q.user.select(id=user_id))
            user.password = bcrypt.generate_password_hash(form.password.data)

            return responses.htmx_response(
                redirect=responses.url_for("login_page"),
                flash=responses.flash("Password updated!", "success"),
            )
        return route