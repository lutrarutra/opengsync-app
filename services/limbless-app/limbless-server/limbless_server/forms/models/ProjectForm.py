from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, TextAreaField, SelectField, FormField
from wtforms.validators import DataRequired, Length

from limbless_db import models
from limbless_db.categories import ProjectStatus

from ... import logger, db
from ..HTMXFlaskForm import HTMXFlaskForm
from ..SearchBar import OptionalSearchBar


class ProjectForm(HTMXFlaskForm):
    _template_path = "forms/project.html"

    name = StringField("Name", validators=[DataRequired(), Length(min=6, max=models.Project.name.type.length)], description="Name of the project")
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=1, max=models.Project.description.type.length)])
    status = SelectField("Status", choices=ProjectStatus.as_selectable(), coerce=int, default=ProjectStatus.DRAFT.id, description="Status of the project")
    group = FormField(OptionalSearchBar, label="Group", description="Group to which the project belongs. All users of that group will be able to see this project.")

    def __init__(self, project: Optional[models.Project] = None, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)
        self.project = project
        if formdata is None and self.project is not None:
            self.__fill_form()

    def __fill_form(self):
        if self.project is None:
            logger.error("Project is not set for form filling.")
            raise ValueError("Project is not set for form filling.")
        self.name.data = self.project.name
        self.description.data = self.project.description
        self.status.data = self.project.status.id
        if self.project.group_id:
            if self.project.group is None:
                logger.error(f"Group with id {self.project.group_id} does not exist.")
                raise ValueError(f"Group with id {self.project.group_id} does not exist.")
            self.group.search_bar.data = self.project.group.name
            self.group.selected.data = self.project.group.id
    
    def validate(self, user: models.User) -> bool:
        if not super().validate():
            return False

        try:
            status = ProjectStatus.get(self.status.data)
        except ValueError:
            self.status.errors = ("Invalid status.",)
            return False

        if self.project is None:
            if status != ProjectStatus.DRAFT:
                self.status.errors = (f"You can only create a project with status {ProjectStatus.DRAFT.name}.",)
                return False
        else:
            if not user.is_insider():
                logger.debug(status)
                logger.debug(self.project.status)
                if status != self.project.status:
                    self.status.errors = ("You don't have permissions to edit the status.",)
                    return False
                
        if self.project is not None:
            user_projects = self.project.owner.projects
        else:
            user_projects = user.projects

        # Creating new project
        if self.project is None:
            if self.name.data in [project.name for project in user_projects]:
                self.name.errors = ("You already have a project with this name.",)
                return False

        # Editing existing project
        else:
            for project in user_projects:
                if project.name == self.name.data:
                    if project.id != self.project.id and project.owner_id == user.id:
                        self.name.errors = ("Owner of the project already has a project with this name.",)
                        return False
                    
        if self.group.selected.data is not None:
            if (group := db.get_group(self.group.selected.data)) is None:
                logger.error(f"Group with id {self.group.selected.data} does not exist.")
                raise ValueError(f"Group with id {self.group.selected.data} does not exist.")
            
            if self.project is not None:
                if db.get_group_user_affiliation(user_id=self.project.owner_id, group_id=group.id) is None:
                    self.group.search_bar.errors = ("Project owner must be part of the group.",)
                    return False
            else:
                if db.get_group_user_affiliation(user_id=user.id, group_id=group.id) is None:
                    self.group.search_bar.errors = ("You must be part of the group.",)
                    return False
        return True
    
    def __create_new_project(self, user_id: int) -> Response:
        project = db.create_project(
            name=self.name.data,  # type: ignore
            description=self.description.data,  # type: ignore
            owner_id=user_id,
            group_id=self.group.selected.data,
        )

        logger.debug(f"Created project {project.name}.")
        flash(f"Created project {project.name}.", "success")

        return make_response(
            redirect=url_for("projects_page.project_page", project_id=project.id),
        )
    
    def __update_existing_project(self) -> Response:
        if self.project is None:
            logger.error("Project is not set for update.")
            raise ValueError("Project is not set for update.")

        self.project.name = self.name.data  # type: ignore
        self.project.description = self.description.data
        self.project.status = ProjectStatus.get(self.status.data)
        self.project.group_id = self.group.selected.data

        self.project = db.update_project(project=self.project)

        flash(f"Updated project {self.project.name}.", "success")

        return make_response(
            redirect=url_for("projects_page.project_page", project_id=self.project.id),
        )
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate(user=user):
            return self.make_response()
        
        if self.project is None:
            return self.__create_new_project(user.id)

        return self.__update_existing_project()
