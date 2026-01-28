from typing import Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, TextAreaField, SelectField, FormField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import ProjectStatus

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm
from ..SearchBar import OptionalSearchBar


class ProjectForm(HTMXFlaskForm):
    _template_path = "forms/project.html"

    identifier = StringField("Identifier", validators=[OptionalValidator(), Length(max=models.Project.identifier.type.length)], description="Identifier of the project. It must be unique across all projects.")
    title = StringField("Title", validators=[DataRequired(), Length(min=6, max=models.Project.title.type.length)], description="Title of the project")
    description = TextAreaField("Description", validators=[DataRequired(), Length(max=2048)])
    status = SelectField("Status", choices=ProjectStatus.as_selectable(), coerce=int, default=ProjectStatus.DRAFT.id, description="Status of the project")
    group = FormField(OptionalSearchBar, label="Group", description="Group to which the project belongs. All users of that group will be able to see this project.")

    def __init__(
        self,
        project: models.Project | None,
        form_type: Literal["create", "edit"],
        formdata: dict | None = None,

    ):
        super().__init__(formdata=formdata)
        self.project = project
        self.form_type = form_type
        match form_type:
            case "create":
                if project is not None:
                    raise exceptions.InternalServerErrorException("Project must be None when creating a new project.")
            case "edit":
                if project is None:
                    raise exceptions.InternalServerErrorException("Project must be set when editing an existing project.")
            case _:
                raise exceptions.InternalServerErrorException("form_type must be either 'create' or 'edit'.")

    def prepare(self):
        if self.project is None:
            return
        
        self.identifier.data = self.project.identifier or ""
        self.title.data = self.project.title
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
                if status != self.project.status:
                    self.status.errors = ("You don't have permissions to edit the status.",)
                    return False
                
        if self.project is not None:
            user_projects = self.project.owner.projects
        else:
            user_projects = user.projects

        # Creating new project
        if self.project is None:
            if self.title.data in [project.title for project in user_projects]:
                self.title.errors = ("You already have a project with this title.",)
                return False
            
            if self.identifier.data:
                if (db.projects.get(self.identifier.data) is not None):
                    self.identifier.errors = ("Project with this identifier already exists.",)
                    return False

        # Editing existing project
        else:
            for project in user_projects:
                if project.title == self.title.data:
                    if project.id != self.project.id and project.owner_id == user.id:
                        self.title.errors = ("Owner of the project already has a project with this title.",)
                        return False
                    
            if self.identifier.data:
                if (prj := db.projects.get(self.identifier.data)) is not None:
                    if prj.id != self.project.id:
                        self.identifier.errors = ("Project with this identifier already exists.",)
                        return False
                    
        if self.group.selected.data is not None:
            if (group := db.groups.get(self.group.selected.data)) is None:
                logger.error(f"Group with id {self.group.selected.data} does not exist.")
                raise ValueError(f"Group with id {self.group.selected.data} does not exist.")
            
            if self.project is not None:
                if not self.project.owner.is_insider() and db.groups.get_user_affiliation(user_id=self.project.owner_id, group_id=group.id) is None:
                    self.group.selected.errors = ("Project owner must be part of the group.",)
                    return False
            else:
                if not user.is_insider() and db.groups.get_user_affiliation(user_id=user.id, group_id=group.id) is None:
                    self.group.selected.errors = ("You must be part of the group.",)
                    return False
                
        if self.title.data:
            if user.is_insider():
                import sqlalchemy as sa
                if db.session.query(models.Project.title).join(
                    models.User,
                    models.User.id == models.Project.owner_id
                ).where(
                    sa.and_(
                        models.Project.id != (self.project.id if self.project else None),
                        models.Project.title == self.title.data.strip(),
                    )
                ).first():
                    self.title.errors = ("There is already a project with this name.",)
                    return False
        return True
    
    def __create_new_project(self, user_id: int) -> Response:
        project = db.projects.create(
            identifier=self.identifier.data if self.identifier.data else None,
            title=self.title.data,  # type: ignore
            description=self.description.data,  # type: ignore
            owner_id=user_id,
            group_id=self.group.selected.data,
        )

        logger.debug(f"Created project {project.title}.")
        flash(f"Created project {project.title}.", "success")

        return make_response(
            redirect=url_for("projects_page.project", project_id=project.id),
        )
    
    def __update_existing_project(self) -> Response:
        if self.project is None:
            logger.error("Project is not set for update.")
            raise ValueError("Project is not set for update.")

        self.project.identifier = self.identifier.data if self.identifier.data else None
        self.project.title = self.title.data  # type: ignore
        self.project.description = self.description.data
        self.project.status = ProjectStatus.get(self.status.data)
        self.project.group_id = self.group.selected.data

        db.projects.update(project=self.project)

        flash(f"Updated project {self.project.title}.", "success")

        return make_response(
            redirect=url_for("projects_page.project", project_id=self.project.id),
        )
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate(user=user):
            return self.make_response()
        
        if self.project is None:
            return self.__create_new_project(user.id)

        return self.__update_existing_project()
