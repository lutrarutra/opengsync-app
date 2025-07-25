from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired

from opengsync_db import models
from opengsync_db.categories import AffiliationType

from .. import db, logger  # noqa F401
from .HTMXFlaskForm import HTMXFlaskForm


class AddUserToGroupForm(HTMXFlaskForm):
    _template_path = "forms/add_user_to_group.html"

    email = StringField("Email", validators=[DataRequired()])
    affiliation_type = SelectField("Affiliation Type", choices=AffiliationType.as_selectable_no_owner(), validators=[DataRequired()], coerce=int, default=AffiliationType.MEMBER.id)

    def __init__(self, group: models.Group, formdata: Optional[dict[str, str]] = None):
        super().__init__(formdata=formdata)
        self.group = group
        self._context["group"] = group

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.email.data:
            self.email.errors = ("Email is required.",)
            return False

        if (user := db.get_user_by_email(self.email.data)) is None:
            self.email.errors = ("User with this email does not exist.",)
            return False
        
        if AffiliationType.get(self.affiliation_type.data) == AffiliationType.OWNER:
            self.affiliation_type.errors = ("Owner affiliation type is not allowed.",)
            return False

        if db.get_group_user_affiliation(user_id=user.id, group_id=self.group.id) is not None:
            self.email.errors = ("User is already in this group.",)
            return False

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if (user := db.get_user_by_email(self.email.data)) is None:  # type: ignore
            logger.error(f"User with email {self.email.data} not found.")
            raise Exception(f"User with email {self.email.data} not found.")
        
        self.group = db.add_user_to_group(user_id=user.id, group_id=self.group.id, affiliation_type=AffiliationType.get(self.affiliation_type.data))
        
        flash("User added to group.", "success")
        return make_response(redirect=url_for("groups_page.group", group_id=self.group.id))
        
