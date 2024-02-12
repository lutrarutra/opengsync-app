from typing import Optional

from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField, StringField, SelectField
from wtforms.validators import DataRequired, Length, ValidationError, Email, EqualTo

from .. import bcrypt, db, models
from ..categories import UserRole
from ..core.DBSession import DBSession
from ..core.DBHandler import DBHandler


class ResetPasswordForm(FlaskForm):
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        return validated, self
    

class UserForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=128)])
    role = SelectField("Role", choices=UserRole.as_selectable(), default=UserRole.CLIENT.value.id, validators=[DataRequired(), Length(max=64)], coerce=int)

    def custom_validate(self, db_handler: DBHandler, current_user: models.User) -> tuple[bool, "UserForm"]:
        validated = self.validate()
        if not validated:
            return False, self
        
        if db_handler.get_user_by_email(self.email.data):
            self.email.errors = ("Email already registered.",)
            validated = False

        try:
            if (user_role := UserRole.get(self.role.data)) is None:
                self.role.errors = ("Invalid role.",)
                validated = False

            elif current_user.role_type != UserRole.ADMIN and user_role == UserRole.ADMIN:
                self.role.errors = ("Only an admin can create another admin.",)
                validated = False
        except ValueError:
            self.role.errors = ("Invalid role.",)
            validated = False
            
        return validated, self


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])

    def custom_validate(self) -> tuple[bool, "LoginForm"]:
        validated = self.validate()
        return validated, self
        
    def login(self) -> tuple[Optional[models.User], "LoginForm"]:
        user = db.db_handler.get_user_by_email(self.email.data)
        # invalid email
        if not user:
            self.email.errors = ("Invalid email or password.",)
            self.password.errors = ("Invalid email or password.",)
            return None, self

        # invalid password
        if not bcrypt.check_password_hash(user.password, self.password.data):
            self.email.errors = ("Invalid email or password.",)
            self.password.errors = ("Invalid email or password.",)
            return None, self
        
        return user, self


class RegisterForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=128)])
        
    def custom_validate(self, db_handler: DBHandler) -> tuple[bool, "RegisterForm"]:
        validated = self.validate()
        if not validated:
            return False, self
        
        domain = self.email.data.split("@")[-1]
        if domain not in {"cemm.at", "cemm.oeaw.ac.at"}:
            self.email.errors = ("Specified email domain is not white-listed. Please contact us at bsf@cemm.at to register.",)
            validated = False
        
        elif db_handler.get_user_by_email(self.email.data):
            self.email.errors = ("Email already registered.",)
            validated = False
            
        return validated, self


class CompleteRegistrationForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired(), Length(max=64)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    def custom_validate(
        self, db_handler: DBHandler
    ) -> tuple[bool, "CompleteRegistrationForm"]:
        
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self