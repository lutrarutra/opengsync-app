

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import FormField

from opengsync_db import models

from .. import logger, db
from .HTMXFlaskForm import HTMXFlaskForm
from .SearchBar import SearchBar


class AddProjectAssigneeForm(HTMXFlaskForm):
    _template_path = "forms/add-project-assignee.html"

    user = FormField(SearchBar, label="Select User")

    def __init__(self, project: models.Project, current_user: models.User, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.project = project
        self.current_user = current_user
        self._context["project"] = project

    def prepare(self) -> None:
        if self.current_user not in self.project.assignees:
            self.user.selected.data = self.current_user.id
            self.user.search_bar.data = self.current_user.name

    def validate(self):
        if not super().validate():
            return False

        if self.user.selected.data is None:
            self.user.selected.errors = ("Please select a user.",)
            return False

        assignee = db.users[self.user.selected.data]

        if not assignee.is_insider():
            self.user.selected.errors = ("Only insider users can be assigned to projects.",)
            return False
        
        if assignee in self.project.assignees:
            self.user.selected.errors = (f"User {assignee.name} is already an assignee in this project.",)
            return False
        
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        assignee = db.users[self.user.selected.data]
        self.project.assignees.append(assignee)
        db.projects.update(self.project)
        
        flash(f"Assignee Added Successfully!", "success")
        return make_response(redirect=url_for("projects_page.project", project_id=self.project.id, tab="project-assignees-tab"))