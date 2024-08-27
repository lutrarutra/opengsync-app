from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length

from limbless_db import models
from limbless_db.categories import GroupType
from ... import logger, db
from ..HTMXFlaskForm import HTMXFlaskForm


class GroupForm(HTMXFlaskForm):
    _template_path = "forms/group.html"
    _form_label = "group_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=models.Group.name.type.length)])
    group_type = SelectField("Type", choices=GroupType.as_selectable(), validators=[DataRequired()], coerce=int)

    def __init__(self, formdata: Optional[dict[str, Any]] = None, group: Optional[models.Group] = None):
        super().__init__(formdata=formdata)
        self.group = group
        if group is not None:
            self.__fill_form(group)

    def __fill_form(self, group: models.Group):
        self.name.data = group.name
        self.group_type.data = group.type.id
    
    def validate(self, group: Optional[models.Group] = None) -> bool:
        if not super().validate():
            return False

        # Creating new group
        if group is None:
            # TODO: check if name is taken
            pass

        # Editing existing group
        else:
            pass

        return True
    
    def __create_new_group(self, user: models.User) -> Response:
        group = db.create_group(
            name=self.name.data,  # type: ignore
            user_id=user.id,
            type=GroupType.get(self.group_type.data),
        )

        flash(f"Created group {group.name}.", "success")

        return make_response(redirect=url_for("groups_page.group_page", group_id=group.id))
    
    def __update_existing_group(self, group: models.Group) -> Response:
        group.name = self.name.data  # type: ignore
        group.type_id = GroupType.get(self.group_type.data).id

        group = db.update_group(group)

        logger.debug(f"Updated group {group.name}.")
        flash(f"Updated group {group.name}.", "success")

        return make_response(redirect=url_for("groups_page.group_page", group_id=group.id),)
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate(group=self.group):
            return self.make_response()
        
        if self.group is None:
            return self.__create_new_group(user=user)

        return self.__update_existing_group(self.group)
