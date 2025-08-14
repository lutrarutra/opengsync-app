from flask import flash, url_for, Response
from flask_htmx import make_response
from wtforms import PasswordField
from wtforms.validators import DataRequired, Length, EqualTo

from opengsync_db import models

from ... import bcrypt, db, serializer, logger
from ..HTMXFlaskForm import HTMXFlaskForm


class ResetPasswordForm(HTMXFlaskForm):
    _template_path = "forms/auth/reset_password.html"

    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True
    
    def process_request(self, **context) -> Response:
        token = context["token"]
        if (data := models.User.verify_reset_token(token=token, serializer=serializer)) is None:
            flash("Invalid or expired token.", "danger")
            return self.make_response(**context)
        
        user_id, email, hash = data
        context["email"] = email
        
        if not self.validate():
            return self.make_response(**context)

        if (user := db.users.get(user_id)) is None:
            flash("User not found.", "danger")
            return self.make_response(**context)
        
        if user.email != email:
            flash("Invalid email.", "danger")
            return self.make_response(**context)
        
        if user.password != hash:
            flash("Invalid password.", "danger")
            return self.make_response(**context)
        
        hashed_password = bcrypt.generate_password_hash(self.password.data).decode("utf-8")
        user.password = hashed_password
        user = db.users.update(user)
        logger.info(f"Password reset for {user.email}")
        flash("Password updated!", "success")
        return make_response(redirect=url_for("auth_page.auth"))