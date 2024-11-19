from flask import flash, url_for, Response
from flask_login import login_user
from flask_htmx import make_response
from flask_mail import Message
from wtforms import EmailField, PasswordField, StringField, SelectField
from wtforms.validators import DataRequired, Length, Email, EqualTo

from limbless_db.categories import UserRole
from limbless_db import models
from .. import bcrypt, db, serializer, logger, EMAIL_SENDER, mail, DOMAIN_WHITE_LIST
from .HTMXFlaskForm import HTMXFlaskForm


class ResetPasswordForm(HTMXFlaskForm):
    _template_path = "forms/reset_password.html"

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

        if (user := db.get_user(user_id)) is None:
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
        db.update_user(user)
        flash("Password updated!", "success")
        return make_response(redirect=url_for("auth_page.auth_page"))
    

class UserForm(HTMXFlaskForm):
    _template_path = "forms/user.html"
    _form_label = "user_form"

    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=models.User.email.type.length)])  # type: ignore
    role = SelectField("Role", choices=UserRole.as_selectable(), default=UserRole.CLIENT.id, validators=[DataRequired()], coerce=int)

    def validate(self, user: models.User) -> bool:
        if not super().validate():
            return False
        
        if not user.is_insider():
            self.email.errors = ("Your account does not have rights to create a new user.",)
            return False
        
        if db.get_user_by_email(self.email.data):  # type: ignore
            self.email.errors = ("Email already registered.",)
            return False

        try:
            if (user_role := UserRole.get(self.role.data)) is None:
                self.role.errors = ("Invalid role.",)
                return False

            elif user.role != UserRole.ADMIN and user_role != UserRole.CLIENT:
                self.role.errors = ("Only an admin can create another insider.",)
                return False
            
        except ValueError:
            self.role.errors = ("Invalid role.",)
            return False
            
        return True
    
    def process_request(self, **context) -> Response:
        user: models.User = context["user"]
        if not self.validate(user):
            return self.make_response(**context)
        
        email = self.email.data.strip()  # type: ignore
        user_role = UserRole.get(self.role.data)

        token = models.User.generate_registration_token(email=email, role=user_role, serializer=serializer)

        url = url_for("auth_page.register_page", token=token, _external=True)
        msg = Message(
            "Limbless Registration",
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
        return make_response(redirect=url_for("index_page"))


class LoginForm(HTMXFlaskForm):
    _template_path = "forms/login.html"
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

    def process_request(self, **context) -> Response:
        dest = context.get("next", url_for("index_page"))
        if not self.validate():
            return self.make_response(**context)
        
        user = db.get_user_by_email(self.email.data)  # type: ignore
        login_user(user)

        flash("Login successful.", "success")
        return make_response(redirect=dest)
    

class RegisterForm(HTMXFlaskForm):
    _template_path = "forms/register.html"
    _form_label = "register_form"
    
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=models.User.email.type.length)])  # type: ignore

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        domain = self.email.data.split("@")[-1]  # type: ignore
        if domain not in DOMAIN_WHITE_LIST:
            self.email.errors = (f"Specified email domain is not in white-list ({', '.join(DOMAIN_WHITE_LIST)}). Please contact us at bsf@cemm.at to register manually.",)
            return False
        
        elif db.get_user_by_email(self.email.data) is not None:  # type: ignore
            self.email.errors = ("Email already registered.",)
            return False
            
        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        email = self.email.data.strip()  # type: ignore
        token = models.User.generate_registration_token(
            email=email, role=UserRole.CLIENT, serializer=serializer
        )
        msg = Message(
            "Limbless Registration",
            sender=EMAIL_SENDER,
            recipients=[email],
            body=f"""Click the following link to register:\n
            {url_for("auth_page.register_page", token=token, _external=True)}
            """
        )
        mail.send(msg)

        flash("Email sent. Check your email for registration link.", "info")
        logger.info(f"Registration email sent to {email}")
        return make_response(redirect=url_for("index_page"))


class CompleteRegistrationForm(HTMXFlaskForm):
    _template_path = "forms/complete_register.html"
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
