from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, AsyncSession
from opengsync_db.categories import UserRole

from ...core import responses, secrets, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm

class LoginForm(HTMXForm):
    """Login form handler — validation, rendering, and response logic."""

    template_path = "forms/auth/login.html"

    email = inputs.string.StringInputField("Email", placeholder="Enter your email")
    password = inputs.string.PasswordInputField("Password",  placeholder="Enter your password")

    @staticmethod
    async def process_request(
        request: Request,
        response: Response,
        session: AsyncSession = Depends(dependencies.db_session), 
        bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
    ) -> Response:
        form = LoginForm(request)
        await form.validate()
        
        if (user := await session.first(Q.user.select(email=form.email.data))) is None:
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
        if user.role == UserRole.DEACTIVATED:
            form.email.errors.append("Account is deactivated. Please contact us to activate your account.")
            raise exc.FormValidationException(form)

        if user.role == UserRole.TEMPORARY:
            user.role = UserRole.DEACTIVATED
            form.email.errors.append("Account is deactivated. Please contact us to activate your account.")
            raise exc.FormValidationException(form)

        response.set_cookie(
            key="access_token",
            value=secrets.create_login_token(user),
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,  # 7 days
        )

        return await responses.htmx_response(redirect=responses.url_for("dashboard"), response=response)
