from fastapi import Request, Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, AsyncSession, models
from opengsync_db.categories import UserRole

from ...core import responses, secrets, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm


class CompleteRegistrationForm(HTMXForm):
    """Register form handler — validation, rendering, and response logic."""

    template_path = "forms/auth/complete_register.html"

    email = inputs.string.EmailInputField("Email", read_only=True)
    first_name = inputs.string.StringInputField("First Name", max_length=models.User.first_name.type.length)
    last_name = inputs.string.StringInputField("Last Name", max_length=models.User.last_name.type.length)
    password = inputs.string.PasswordInputField("Password", min_length=8, autocomplete="new-password")
    confirm = inputs.string.PasswordInputField("Confirm Password", autocomplete="new-password")

    async def prepare(self):
        token = self.request.path_params.get("token")
        if token is not None:
            if (data := secrets.verify_registration_token(token=token)) is not None:
                email, role = data
                self.email.data = email
            else:
                self.email.errors.append("Token expired or invalid.")
                raise exc.FormValidationException(self)
        else:
            self.email.errors.append("Token expired or invalid.")
            raise exc.FormValidationException(self)

    @staticmethod
    async def process_request(
        request: Request,
        token: str,
        session: AsyncSession = Depends(dependencies.db_session),
        bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
    ) -> Response:
        form = CompleteRegistrationForm(request)
        logger.debug(await request.form())
        await form.validate()
        
        if (data := secrets.verify_registration_token(token=token)) is None:
            form.email.errors.append("Token expired or invalid.")
            raise exc.FormValidationException(form)
        
        email, role = data
        if await session.exists(Q.user.select(email=email)):
            form.email.errors.append("User already exists.")
            raise exc.FormValidationException(form)
        if email != form.email.data:
            form.email.errors.append("Token expired or invalid.")
            raise exc.FormValidationException(form)
        
        user = await session.save(Q.user.create(
            email=email,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            hashed_password=bcrypt.generate_password_hash(form.password.data),
            role=UserRole.get(role)
        ))

        logger.info(f"User {user.email} completed registration.")
        return await responses.htmx_response(redirect="login_page")
    
    @property
    def token(self) -> str:
        return self.request.path_params["token"]
        


