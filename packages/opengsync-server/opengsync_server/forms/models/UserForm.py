from typing import Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length

from opengsync_db import models
from opengsync_db.categories import ProjectStatus, UserRole

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm

class UserForm(HTMXFlaskForm):
    _template_path = "forms/user.html"

    first_name = StringField("First Name", validators=[DataRequired(), Length(max=models.User.first_name.type.length)])  # type: ignore
    last_name = StringField("Last Name", validators=[DataRequired(), Length(max=models.User.last_name.type.length)])  # type: ignore
    role = SelectField("Role", choices=[], coerce=int, description="Role of the user in the system.")

    def __init__(
        self,
        user: models.User,
        current_user: models.User,
        formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        self.user = user
        self.current_user = current_user
        logger.debug(formdata)

        if self.current_user.is_admin or (self.current_user.id == self.user.id and self.user.is_insider):
            self.role.choices = UserRole.as_selectable()  # type: ignore
        elif self.current_user.is_insider:
            allowed_roles = [UserRole.CLIENT, UserRole.DEACTIVATED]
            self.role.choices = [(role.id, role.display_name) for role in allowed_roles]  # type: ignore
        else:
            self.role.choices = [(UserRole.CLIENT.id, UserRole.CLIENT.display_name)]
            self.role.data = UserRole.CLIENT.id

    def prepare(self):
        self.first_name.data = self.user.first_name
        self.last_name.data = self.user.last_name
        self.role.data = self.user.role.id

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.current_user.is_insider:
            if self.role.data != UserRole.CLIENT.id:
                self.role.errors = ("You do not have permission to set this role.",)
                return False
            
        elif not self.current_user.is_admin:
            if self.role.data not in [UserRole.CLIENT.id, UserRole.DEACTIVATED.id] and self.current_user.role != self.user.role:
                self.role.errors = ("You do not have permission to set this role.",)
                return False
        
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.user.first_name = self.first_name.data.strip()  # type: ignore
        self.user.last_name = self.last_name.data.strip()  # type: ignore
        if (role := UserRole.get(self.role.data)) is None:
            self.role.errors = ("Invalid role.",)
            return self.make_response()
        if self.current_user.is_admin:
            self.user.role = role

        flash("User updated successfully.", "success")
        logger.info(f"User ID {self.user.id} updated by user ID {self.current_user.id}")
        return make_response(redirect=url_for("user_page", user_id=self.user.id))