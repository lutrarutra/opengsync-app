from flask import flash, Response
from flask_login import login_user
from flask_htmx import make_response
from wtforms import EmailField, PasswordField
from wtforms.validators import DataRequired, Email

from ... import bcrypt, db, logger  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class LoginForm(HTMXFlaskForm):
    _template_path = "forms/auth/login.html"
    _form_label = "login_form"

    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
        
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        # invalid email
        if (user := db.get_user_by_email(self.email.data)) is None:  # type: ignore
            self.email.errors = ("Invalid email or password.",)
            self.password.errors = ("Invalid email or password.",)
            return False

        # invalid password
        if not bcrypt.check_password_hash(user.password, self.password.data):
            self.email.errors = ("Invalid email or password.",)
            self.password.errors = ("Invalid email or password.",)
            return False
        
        return True

    def process_request(self, dest: str = "/") -> Response:
        if not self.validate():
            return self.make_response()
        
        user = db.get_user_by_email(self.email.data)  # type: ignore
        login_user(user)

        flash("Login successful.", "success")
        return make_response(redirect=dest)