from flask import flash, url_for, Response, render_template
from flask_htmx import make_response
from wtforms import EmailField, SelectField
from wtforms.validators import DataRequired, Length, Email, Optional as OptionalValidator

from opengsync_db.categories import UserRole
from opengsync_db import models

from ... import db, serializer, logger, mail_handler
from ...core import runtime
from ..HTMXFlaskForm import HTMXFlaskForm
    

class RegisterUserForm(HTMXFlaskForm):
    _template_path = "forms/auth/register.html"

    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=models.User.email.type.length)])  # type: ignore
    role = SelectField("Role", choices=UserRole.as_selectable(), default=UserRole.CLIENT.id, validators=[OptionalValidator()], coerce=int)

    def __init__(self, formdata: dict[str, str] | None = None):
        super().__init__(formdata)

    def validate(self, user: models.User | None) -> bool:
        if not super().validate():
            return False
        
        if not self.email.data:
            self.email.errors = ("Email is required.",)
            return False
        
        if runtime.app.email_domain_white_list is not None:
            if self.email.data.split("@")[-1] not in runtime.app.email_domain_white_list:
                self.email.errors = ("Specified email domain is not allowed. Please contact us.",)
                return False
        
        if db.users.get_with_email(self.email.data):  # type: ignore
            self.email.errors = ("Email already registered.",)
            return False

        try:
            if (user_role := UserRole.get(self.role.data)) is None:
                self.role.errors = ("Invalid role.",)
                return False

            elif user is None or user.role != UserRole.ADMIN:
                if user_role != UserRole.CLIENT:
                    self.role.errors = ("You don't have permissions to create user with this role",)
                    return False
            
        except ValueError:
            self.role.errors = ("Invalid role.",)
            return False
            
        return True
    
    def process_request(self, user: models.User | None) -> Response:
        if not self.validate(user):
            return self.make_response()
        
        email = self.email.data.strip()  # type: ignore
        user_role = UserRole.get(self.role.data)

        token = models.User.generate_registration_token(email=email, role=user_role, serializer=serializer)

        link = url_for("auth_page.register", token=token, _external=True)

        if not mail_handler.send_email(
            recipients=email,
            subject="OpeNGSync User Registration",
            body=render_template("email/register-user.html", link=link),
            mime_type="html"
        ):
            self.email.errors = ("Failed to send registration email. Please contact administrator.",)
            logger.error(f"Failed to send registration email to '{email}'")
            return self.make_response()

        flash("Email sent. Check your email for registration link.", "info")
        logger.info(f"Registration email sent to {email}")
        return make_response(redirect=url_for("dashboard"))