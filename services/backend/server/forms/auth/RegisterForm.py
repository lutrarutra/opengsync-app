from fastapi import Request, Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, SyncSession, models
from opengsync_db.categories import UserRole

from ...core import responses, secrets, dependencies, exceptions as exc, config, mailer
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, htmx_route


class RegisterForm(HTMXForm):
    """Register form handler — validation, rendering, and response logic."""

    template_path = "forms/auth/register.html"

    email = inputs.string.EmailInputField("Email")
    role = inputs.selectable.SelectableInputField("Role", options=UserRole.as_selectable(), default=UserRole.CLIENT.id)

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: RegisterForm = Depends(RegisterForm.Init()),
            _ = Depends(dependencies.get_user),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Register(cls) -> RouteFunc:
        def route(
            request: Request,
            current_user: models.User | None = Depends(dependencies.get_user),
            mailer: mailer.Mailer = Depends(dependencies.mail_client),
            session: SyncSession = Depends(dependencies.db_session),
            form: RegisterForm = Depends(RegisterForm.Validate()),
        ) -> Response:
            # Email domain whitelist check
            if current_user is None or not current_user.is_insider:
                if config.settings.app_config.email_domain_white_list:
                    if form.email.data.split("@")[-1].lower() not in [domain.lower() for domain in config.settings.app_config.email_domain_white_list]:
                        form.email.errors.append("Specified email domain is not found in white-list. Please contact us.")
                        raise exc.FormValidationException(form)

            # Role validation
            try:
                if (user_role := UserRole.get(form.role.data)) is None:
                    form.role.errors.append("Invalid role.")
                    raise exc.FormValidationException(form)

                if current_user is None or not current_user.is_insider:
                    if user_role != UserRole.CLIENT:
                        form.role.errors.append("You don't have permissions to create user with this role")
                        raise exc.FormValidationException(form)
                elif current_user.role != UserRole.ADMIN:
                    if user_role not in (UserRole.CLIENT, UserRole.DEACTIVATED):
                        form.role.errors.append("You don't have permissions to create user with this role")
                        raise exc.FormValidationException(form)
            except ValueError:
                form.role.errors.append("Invalid role.")
                raise exc.FormValidationException(form)

            # Process registration
            if (user := session.first(Q.user.select(email=form.email.data))) is None:
                try:
                    mailer.send_welcome_back(form.email.data)
                except Exception as e:
                    logger.error(f"Failed to send welcome back email to '{form.email.data}':", exception=e)
                    form.email.errors.append("Failed to send registration email. Please contact administrator.")
                    raise e
                return responses.htmx_response(redirect=responses.url_for("login_page"))

            token = secrets.generate_registration_token(email=form.email.data, role=user.role)
            link = request.url_for("complete_registration_page", token=token)
            try:
                mailer.send_registration(form.email.data, link)
            except Exception as e:
                logger.error(f"Failed to send registration email to '{form.email.data}':", exception=e)
                form.email.errors.append("Failed to send registration email. Please contact administrator.")
                raise e

            return responses.htmx_response(redirect=responses.url_for("login_page"))
        return route
