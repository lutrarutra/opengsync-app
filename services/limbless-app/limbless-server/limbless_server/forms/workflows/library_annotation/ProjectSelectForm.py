from typing import Optional, Literal

from flask import Response
from wtforms import StringField, FormField, TextAreaField
from wtforms.validators import Optional as OptionalValidator, Length

from limbless_db import models

from .... import db, logger  # noqa F401
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from ...MultiStepForm import MultiStepForm
from .LibraryAnnotationForm import LibraryAnnotationForm
from .SpecifyAssayForm import SpecifyAssayForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm


class ProjectSelectForm(HTMXFlaskForm, MultiStepForm):
    _template_path = "workflows/library_annotation/sas-1.1.html"

    existing_project = FormField(OptionalSearchBar, label="Select Existing Project")
    new_project = StringField("Create New Project", validators=[OptionalValidator(), Length(min=6, max=models.Project.name.type.length)])
    project_description = TextAreaField("Project Description", validators=[OptionalValidator(), Length(max=models.Project.description.type.length)], description="New projects only: brief context/background of the project.")

    def __init__(self, seq_request: models.SeqRequest, workflow_type: Literal["raw", "pooled", "tech"], formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        MultiStepForm.__init__(self, uuid=None, dirname="library_annotation")
        self.workflow_type = workflow_type
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self._context["workflow_type"] = workflow_type
    
    def validate(self, user: models.User) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        if not self.new_project.data and self.existing_project.selected.data is None:
            self.new_project.errors = ("Please select or create a project.",)
            self.existing_project.selected.errors = ("Please select or create a project.",)
            return False
        
        if self.existing_project.selected.data is not None and self.existing_project.search_bar.data is None:
            self.existing_project.search_bar.errors = ("Please select a project.",)
            return False
        
        if self.new_project.data and not self.project_description.data:
            self.project_description.errors = ("Please, provide brief description of the project.",)
            return False

        if self.existing_project.selected.data is not None and self.project_description.data:
            self.project_description.errors = ("Project description is not needed if using existing project.",)
            return False
        
        self.project_id: Optional[int] = self.existing_project.selected.data
        self.project_name: str
        if self.project_id is not None:
            self.project_name = self.existing_project.search_bar.data
        else:
            if self.new_project.data is None:
                self.new_project.errors = ("Please enter a project name.",)
                return False
            self.project_name = self.new_project.data.strip()
        
        if self.project_id is None:
            if self.project_name in [project.name for project in user.projects]:
                self.new_project.errors = ("You already have a project with this name.",)
                return False

        return validated
    
    def process_request(self, user: models.User) -> Response:
        validated = self.validate(user)
        if not validated:
            return self.make_response()

        self.metadata["project_name"] = self.project_name
        self.metadata["workflow"] = "library_annotation"
        self.metadata["project_id"] = self.project_id
        self.metadata["workflow_type"] = self.workflow_type
        self.metadata["seq_request_id"] = self.seq_request.id
        self.metadata["user_id"] = user.id
        self.metadata["project_description"] = self.project_description.data
        self.update_data()

        if self.workflow_type == "tech":
            form = SpecifyAssayForm(seq_request=self.seq_request, uuid=self.uuid, previous_form=self)
        elif self.workflow_type == "pooled":
            form = PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid, previous_form=self)
        else:
            form = LibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid, previous_form=self)
        
        return form.make_response()
