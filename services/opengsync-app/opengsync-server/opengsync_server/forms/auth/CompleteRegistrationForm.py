from flask import flash, url_for, Response
from flask_htmx import make_response
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Length, EqualTo

from opengsync_db import models

from ... import bcrypt, db, serializer, logger
from ..HTMXFlaskForm import HTMXFlaskForm


class CompleteRegistrationForm(HTMXFlaskForm):
    _template_path = "forms/auth/complete_register.html"
    _form_label = "complete_registration_form"

    first_name = StringField("First Name", validators=[DataRequired(), Length(max=models.User.first_name.type.length)])  # type: ignore
    last_name = StringField("Last Name", validators=[DataRequired(), Length(max=models.User.last_name.type.length)])  # type: ignore
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True
        
    def process_request(self, **context) -> Response:
        token = context["token"]
        if (data := models.User.verify_registration_token(token=token, serializer=serializer)) is None:
            flash("Invalid or expired token.", "danger")
            return self.make_response(**context)
        
        email, user_role = data
        context["email"] = email
        context["user_role"] = user_role

        if not self.validate():
            return self.make_response(**context)

        hashed_password = bcrypt.generate_password_hash(self.password.data).decode("utf-8")

        user = db.create_user(
            email=email,
            hashed_password=hashed_password,
            first_name=self.first_name.data,  # type: ignore
            last_name=self.last_name.data,  # type: ignore
            role=user_role,
        )

        flash("Registration completed!", "success")
        logger.info(f"Registration completed for {user.email}")
        return make_response(redirect=url_for("auth_page.auth_page"))