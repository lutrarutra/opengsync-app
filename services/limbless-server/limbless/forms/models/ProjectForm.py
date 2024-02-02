from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length

from ... import logger, db, models
from ...core.DBSession import DBSession
from ..HTMXFlaskForm import HTMXFlaskForm


class ProjectForm(HTMXFlaskForm):
    _template_path = "forms/project.html"
    _form_label = "project_form"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=64)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=1, max=1024)])

    def __init__(self, formdata: Optional[dict[str, Any]] = None, project: Optional[models.Project] = None):
        super().__init__(formdata=formdata)
        if project is not None:
            self.__fill_form(project)

    def __fill_form(self, project: models.Project):
        self.name.data = project.name
        self.description.data = project.description
    
    def validate(self, user_id: int, project: Optional[models.Project] = None) -> bool:
        if not super().validate():
            return False
        
        with DBSession(db.db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
                return False

            user_projects = user.projects

            # Creating new project
            if project is None:
                if self.name.data in [project.name for project in user_projects]:
                    self.name.errors = ("You already have a project with this name.",)
                    return False

            # Editing existing project
            else:
                for project in user_projects:
                    if project.name == self.name.data:
                        if project.id != project.id and project.owner_id == user_id:
                            self.name.errors = ("You already have a library with this name.",)
                            return False

        return True
    
    def __create_new_project(self, user_id: int) -> Response:
        project = db.db_handler.create_project(
            name=self.name.data,
            description=self.description.data,
            owner_id=user_id
        )

        logger.debug(f"Created project {project.name}.")
        flash(f"Created project {project.name}.", "success")

        return make_response(
            redirect=url_for("projects_page.project_page", project_id=project.id),
        )
    
    def __update_existing_project(self, project: models.Project) -> Response:
        project = db.db_handler.update_project(
            project_id=project.id,
            name=self.name.data,
            description=self.description.data,
        )

        logger.debug(f"Updated project {project.name}.")
        flash(f"Updated project {project.name}.", "success")

        return make_response(
            redirect=url_for("projects_page.project_page", project_id=project.id),
        )
    
    def process_request(self, **context) -> Response:
        user_id: int = context["user_id"]
        project: Optional[models.Project] = context.get("project")

        if not self.validate(user_id=user_id, project=project):
            return self.make_response(**context)
        
        if project is None:
            return self.__create_new_project(user_id)

        return self.__update_existing_project(project)
