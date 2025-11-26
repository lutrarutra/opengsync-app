from flask import flash, Response, url_for
from flask_login import login_user
from flask_htmx import make_response
from wtforms import EmailField, PasswordField
from wtforms.validators import DataRequired, Email

from opengsync_db.categories import UserRole

from ... import bcrypt, db, logger  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm
from ...core import runtime


class LoginForm(HTMXFlaskForm):
    _template_path = "forms/auth/login.html"
    _form_label = "login_form"

    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
        
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True

    def process_request(self, dest: str | None = None) -> Response:
        if not self.validate():
            return self.make_response()
        
        # invalid email
        if (user := db.users.get_with_email(self.email.data)) is None:  # type: ignore
            self.email.errors = ("Invalid email or password.",)
            self.password.errors = ("Invalid email or password.",)
            return self.make_response()

        # invalid password
        if not bcrypt.check_password_hash(user.password, self.password.data):
            self.email.errors = ("Invalid email or password.",)
            self.password.errors = ("Invalid email or password.",)
            return self.make_response()
        
        if user.role == UserRole.DEACTIVATED:
            self.email.errors = ("Account is deactivated. Please contact us.",)
            return self.make_response()
        
        runtime.session.clear()
        login_user(user)
        runtime.app.session_interface.regenerate(runtime.session)  # type: ignore

        flash("Login successful.", "success")
        return make_response(redirect=dest or url_for("dashboard"))