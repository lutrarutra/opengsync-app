from flask import flash, url_for, Response
from flask_htmx import make_response
from wtforms import PasswordField, EmailField
from wtforms.validators import DataRequired, Length, EqualTo

from ... import bcrypt, db, serializer, logger
from ...core import runtime, tokens
from ..HTMXFlaskForm import HTMXFlaskForm


class ResetPasswordForm(HTMXFlaskForm):
    _template_path = "forms/auth/reset_password.html"

    email = EmailField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    def __init__(self, token: str, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.token = token

    def prepare(self):
        if (data := tokens.verify_reset_token(token=self.token, serializer=serializer)) is not None:
            user_id, email, hash = data
            if (user := db.users.get(user_id)) is None:
                self.email.errors = ("Token expired or invalid.",)
                return
            if user.email != email:
                self.email.errors = ("Token expired or invalid.",)
                return
            if user.password != hash:
                self.email.errors = ("Token expired or invalid.",)
                return
            self.email.data = email
        else:
            self.email.errors = ("Token expired or invalid.",)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if (data := tokens.verify_reset_token(token=self.token, serializer=serializer)) is None:
            self.email.errors = ("Token expired or invalid.",)
            return False
        
        user_id, email, hash = data
        if (user := db.users.get(user_id)) is None:
            self.email.errors = ("Token expired or invalid.",)
            return False
        
        if user.email != email:
            self.email.errors = ("Token expired or invalid.",)
            return False
        
        if user.password != hash:
            self.email.errors = ("Token expired or invalid.",)
            return False
        
        self.user = user

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        hashed_password = bcrypt.generate_password_hash(self.password.data).decode("utf-8")
        self.user.password = hashed_password
        db.users.update(self.user)
        logger.info(f"Password reset for {self.user.id}")
        runtime.app.delete_user_sessions(self.user.id)
        runtime.session.clear()
        flash("Password updated!", "success")
        return make_response(redirect=url_for("auth_page.auth"))