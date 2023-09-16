from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError

from .. import logger
from ..core.DBHandler import DBHandler


class ProjectForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=64)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=1, max=1024)])
        
    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        project_id: int | None = None,
    ) -> tuple[bool, "ProjectForm"]:

        validated = self.validate()
        if not validated:
            return False, self

        db_handler.open_session()
        if (user := db_handler.get_user(user_id)) is None:
            logger.error(f"User with id {user_id} does not exist.")
            db_handler.close_session()
            return False, self

        user_projects = user.projects

        # Creating new project
        if project_id is None:
            if self.name.data in [project.name for project in user_projects]:
                self.name.errors = ("You already have a project with this name.",)
                validated = False

        # Editing existing project
        else:
            for project in user_projects:
                if project.name == self.name.data:
                    if project.id != project_id and project.owner_id == user_id:
                        self.name.errors = ("You already have a library with this name.",)
                        validated = False

        db_handler.close_session()

        return validated, self
