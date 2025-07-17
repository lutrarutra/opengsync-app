from flask import flash, url_for, Response
from flask_htmx import make_response
from flask_mail import Message
from wtforms import EmailField, SelectField
from wtforms.validators import DataRequired, Length, Email, Optional as OptionalValidator

from opengsync_db.categories import UserRole
from opengsync_db import models

from ... import db, serializer, logger, EMAIL_SENDER, mail
from ..HTMXFlaskForm import HTMXFlaskForm
    

class RegisterUserForm(HTMXFlaskForm):
    _template_path = "forms/auth/register.html"

    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=models.User.email.type.length)])  # type: ignore
    role = SelectField("Role", choices=UserRole.as_selectable(), default=UserRole.CLIENT.id, validators=[OptionalValidator()], coerce=int)

    def __init__(self, user: models.User | None, formdata: dict[str, str] | None = None):
        super().__init__(formdata)
        self._context["user"] = user
        self.user = user

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if db.get_user_by_email(self.email.data):  # type: ignore
            self.email.errors = ("Email already registered.",)
            return False

        try:
            if (user_role := UserRole.get(self.role.data)) is None:
                self.role.errors = ("Invalid role.",)
                return False

            elif self.user is None or self.user.role != UserRole.ADMIN:
                if user_role != UserRole.CLIENT:
                    self.role.errors = ("You don't have permissions to create user with this role",)
                    return False
            
        except ValueError:
            self.role.errors = ("Invalid role.",)
            return False
            
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        email = self.email.data.strip()  # type: ignore
        user_role = UserRole.get(self.role.data)

        token = models.User.generate_registration_token(email=email, role=user_role, serializer=serializer)

        url = url_for("auth_page.register_page", token=token, _external=True)
        msg = Message(
            "OpeNGSync Registration",
            sender=EMAIL_SENDER,
            recipients=[email],
            body=f"""Follow the link to register:\n
            \n
            <a href='{url}'>{url}</a>
            """
        )
        mail.send(msg)

        flash("Email sent. Check your email for registration link.", "info")
        logger.info(f"Registration email sent to {email}")
        return make_response(redirect=url_for("dashboard"))