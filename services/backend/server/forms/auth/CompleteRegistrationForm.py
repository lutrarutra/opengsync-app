from fastapi import Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, SyncSession, models
from opengsync_db.categories import UserRole

from ...core import responses, secrets, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class CompleteRegistrationForm(HTMXForm):
    """Register form handler — validation, rendering, and response logic."""

    template_path = "forms/auth/complete_register.html"

    email = inputs.string.EmailInputField("Email", read_only=True)
    first_name = inputs.string.StringInputField("First Name", max_length=models.User.first_name.type.length)
    last_name = inputs.string.StringInputField("Last Name", max_length=models.User.last_name.type.length)
    password = inputs.string.PasswordInputField("Password", min_length=8, autocomplete="new-password")
    confirm = inputs.string.PasswordInputField("Confirm Password", autocomplete="new-password")

    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token
        self.post_url = responses.url_for("CompleteRegistrationForm.Submit", token=token)

        data = secrets.verify_registration_token(token=token)
        if data is None:
            self.email.errors.append("Token expired or invalid.")
            return

        self.email.data = data[0]
        self.role = data[1]

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(token: str) -> "CompleteRegistrationForm":
            return CompleteRegistrationForm(token=token)
        return dependency

    @htmx_route("GET", "/complete-registration/{token}")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "CompleteRegistrationForm" = Depends(CompleteRegistrationForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/complete-registration/{token}")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
            form: "CompleteRegistrationForm" = Depends(CompleteRegistrationForm.Validate()),
            _ = Depends(dependencies.audit_log)
        ) -> Response:
            data = secrets.verify_registration_token(token=form.token)
            if data is None:
                form.email.errors.append("Token expired or invalid.")
                raise exc.FormValidationException(form)

            email, role = data
            if session.exists(Q.user.select(email=email)):
                form.email.errors.append("User already exists.")
                raise exc.FormValidationException(form)
            if email != form.email.data:
                form.email.errors.append("Token expired or invalid.")
                raise exc.FormValidationException(form)

            user = session.save(Q.user.create(
                email=email,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                hashed_password=bcrypt.generate_password_hash(form.password.data),
                role=UserRole.get(role),
            ), flush=True)

            logger.info(f"User {user.email} completed registration.")
            return responses.htmx_response(
                redirect=responses.url_for("login_page"),
                flash=responses.flash("Registration completed successfully.", "success"),
            )
        return route
        


