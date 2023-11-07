from typing import Literal

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, BooleanField, EmailField
from wtforms.validators import DataRequired, Length, Optional, Email

from .. import logger
from ..categories import LibraryType
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession

class PoolForm(FlaskForm):
    _choises = LibraryType.as_selectable()
    name = StringField("Pool Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        pool_id: int | None = None,
    ) -> tuple[bool, "PoolForm"]:

        validated = self.validate()

        if not validated:
            return False, self
        
        with DBSession(db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
                return False, self

            # Creating new pool
            if pool_id is None:
                if self.name.data in [pool.name for pool in user.pools]:
                    self.name.errors = ("Pool with this name already exists",)
                    validated = False

        return validated, self
