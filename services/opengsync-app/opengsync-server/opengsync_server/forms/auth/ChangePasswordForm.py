from typing import Optional, Any

from flask import Response, flash, url_for
from flask_login import logout_user
from flask_htmx import make_response
from wtforms import PasswordField
from wtforms.validators import DataRequired, Length, EqualTo

from opengsync_db import models

from ... import logger, db, bcrypt
from ..HTMXFlaskForm import HTMXFlaskForm


class ChangePasswordForm(HTMXFlaskForm):
    _template_path = "forms/auth/change_password.html"

    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), Length(min=8), EqualTo("new_password", "Passwords must match.")])

    def __init__(self, user: models.User, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)
        self.user = user
        self._context["user"] = user

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        # Check current password
        if not bcrypt.check_password_hash(self.user.password, self.current_password.data):
            self.current_password.errors = ("Invalid Password",)
            return False

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        # Update password
        hashed_password = bcrypt.generate_password_hash(self.new_password.data).decode("utf-8")
        self.user.password = hashed_password
        self.user = db.update_user(self.user)
        logger.info(f"Password changed for user {self.user.email}")
        flash("Password Changed Successfully!", "success")
        logout_user()
        return make_response(redirect=url_for("auth_page.auth_page"))

    