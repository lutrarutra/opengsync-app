from fastapi import Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession

from ...core import responses, secrets, dependencies, auth, passkeys, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, htmx_route, RouteFunc

class LoginForm(HTMXForm):
    """Login form handler — validation, rendering, and response logic."""

    template_path = "forms/auth/login.html"

    # "webauthn" lets the browser offer saved passkeys in this field's autofill.
    email = inputs.string.StringInputField("Email", placeholder="Enter your email", autocomplete="username webauthn")
    password = inputs.string.PasswordInputField("Password",  placeholder="Enter your password")

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: LoginForm = Depends(LoginForm.Init()),
            current_user_id: int | None = Depends(dependencies.get_user_id),
        ) -> Response:
            if current_user_id is not None:
                return responses.htmx_response(redirect=responses.url_for("dashboard"))

            return form.make_response()
        return route

    @htmx_route("POST")
    def Login(cls) -> RouteFunc:
        def route(
            response: Response,
            session: SyncSession = Depends(dependencies.db_session), 
            bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
            form: LoginForm = Depends(LoginForm.Validate()),
        ) -> Response:
            
            if (user := session.first(Q.user.select(email=form.email.data))) is None:
                form.email.errors.append("Invalid email or password.")
                form.password.errors.append("Invalid email or password.")
                raise exc.FormValidationException(form)

            try:
                if not bcrypt.check_password_hash(user.password, form.password.data):
                    form.email.errors.append("Invalid email or password.")
                    form.password.errors.append("Invalid email or password.")
                    raise exc.FormValidationException(form)
            except ValueError:
                form.password.errors.append("Invalid email or password.")
                raise exc.FormValidationException(form)

            # Check role
            if (rejection := auth.login_rejection(user)) is not None:
                form.email.errors.append(rejection)
                raise exc.FormValidationException(form)

            auth.set_login_cookie(response, user)
            # Tells passkey.js on the next page to offer saving a passkey to the password manager.
            passkeys.set_upgrade_cookie(response)

            return responses.htmx_response(
                redirect=responses.url_for("dashboard"), response=response,
                flash=responses.flash(message="Logged In!", category="success")
            )
        return route
