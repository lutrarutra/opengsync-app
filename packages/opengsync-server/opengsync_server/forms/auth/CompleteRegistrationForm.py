from flask import flash, url_for, Response
from flask_htmx import make_response
from wtforms import PasswordField, StringField, EmailField
from wtforms.validators import DataRequired, Length, EqualTo

from opengsync_db import models

from ... import bcrypt, db, serializer, logger
from ...core import tokens
from ..HTMXFlaskForm import HTMXFlaskForm


class CompleteRegistrationForm(HTMXFlaskForm):
    _template_path = "forms/auth/complete_register.html"

    email = EmailField("Email", validators=[DataRequired()])
    first_name = StringField("First Name", validators=[DataRequired(), Length(max=models.User.first_name.type.length)])  # type: ignore
    last_name = StringField("Last Name", validators=[DataRequired(), Length(max=models.User.last_name.type.length)])  # type: ignore
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    def __init__(self, token: str, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.token = token
        self._email = None
        self._role = None
        if (data := tokens.verify_registration_token(token=self.token, serializer=serializer)) is not None:
            self._email, self._role = data
    
    def prepare(self):
        if self._email is not None:
            if db.users.get_with_email(self._email) is not None:
                self.email.errors = ("Token expired or invalid.",)
                return
            self.email.data = self._email
        else:
            self.email.errors = ("Token expired or invalid.",)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if (data := tokens.verify_registration_token(token=self.token, serializer=serializer)) is None:
            self.email.errors = ("Token expired or invalid.",)
            return False
        
        self._email, self._role = data
        if db.users.get_with_email(self._email) is not None:
            self.email.errors = ("Token expired or invalid.",)
            return False
        if self._email != self.email.data:
            self.email.errors = ("Token expired or invalid.",)
            return False
        
        return True
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        hashed_password = bcrypt.generate_password_hash(self.password.data).decode("utf-8")

        user = db.users.create(
            email=self._email.strip(),  # type: ignore
            hashed_password=hashed_password,
            first_name=self.first_name.data.strip(),  # type: ignore
            last_name=self.last_name.data.strip(),  # type: ignore
            role=self._role,  # type: ignore
        )

        flash("Registration completed!", "success")
        logger.info(f"Registration completed for {user.email}")
        return make_response(redirect=url_for("auth_page.auth"))