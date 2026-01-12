from flask import Response
from wtforms import StringField, FormField, TextAreaField, BooleanField
from wtforms.validators import Optional as OptionalValidator, Length

from opengsync_db import models
from opengsync_server.forms.MultiStepForm import StepFile

from .... import db, logger  # noqa F401
from ...SearchBar import OptionalSearchBar
from ...MultiStepForm import MultiStepForm
from .SampleAnnotationForm import SampleAnnotationForm


class ProjectSelectForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-project_select.html"
    _workflow_name = "library_annotation"
    _step_name = "project_select"

    existing_project = FormField(OptionalSearchBar, label="Select Existing Project")
    new_project = StringField("Create New Project", validators=[OptionalValidator(), Length(min=6, max=models.Project.title.type.length)])
    project_description = TextAreaField("Project Description", validators=[OptionalValidator(), Length(max=2048)], description="New projects only: brief context/background of the project.")
    set_requestor_as_owner = BooleanField(default=True)

    def __init__(self, seq_request: models.SeqRequest, formdata: dict | None = None, uuid: str | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, step_name=ProjectSelectForm._step_name,
            workflow=ProjectSelectForm._workflow_name, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def fill_previous_form(self, previous_form: StepFile):
        if (project_id := previous_form.metadata.get("project_id")) is not None:
            self.existing_project.selected.data = project_id
            self.existing_project.search_bar.data = project.title if (project := db.projects.get(project_id)) is not None else None
        else:
            self.new_project.data = previous_form.metadata.get("project_title")
            self.project_description.data = previous_form.metadata.get("project_description")
    
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
        
        self.project_id: int | None = self.existing_project.selected.data
        self.project_title: str
        if self.project_id is not None:
            self.project_title = self.existing_project.search_bar.data
        else:
            if self.new_project.data is None:
                self.new_project.errors = ("Please enter a project name.",)
                return False
            self.project_title = self.new_project.data.strip()
        
        if self.project_id is None:
            if self.project_title in [project.title for project in user.projects]:
                self.new_project.errors = ("You already have a project with this name.",)
                return False
            
        if self.new_project.data:
            if user.is_insider():
                import sqlalchemy as sa
                if db.session.query(models.Project.title).join(
                    models.User,
                    models.User.id == models.Project.owner_id
                ).where(
                    sa.and_(
                        models.Project.title == self.new_project.data.strip(),
                    )
                ).first():
                    self.new_project.errors = ("There is already a project with this name.",)
                    return False

        return validated
    
    def process_request(self, user: models.User) -> Response:
        validated = self.validate(user)
        if not validated:
            return self.make_response()

        self.metadata["submission_type_id"] = self.seq_request.submission_type.id
        self.metadata["project_title"] = self.project_title
        self.metadata["workflow"] = "library_annotation"
        self.metadata["project_id"] = self.project_id
        self.metadata["seq_request_id"] = self.seq_request.id
        self.metadata["user_id"] = user.id
        self.metadata["project_description"] = self.project_description.data
        self.metadata["project_owner_id"] = self.seq_request.requestor.id if self.set_requestor_as_owner.data and user.is_insider() else user.id
        self.update_data()

        next_form = SampleAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)        
        return next_form.make_response()
