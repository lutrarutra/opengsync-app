from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import exceptions as exc, dependencies, responses
from ....components import inputs
from ..HTMXWorkflowStep import HTMXWorkflowStep
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from ...HTMXForm import RouteFunc, FormFunc, htmx_route

class ProjectSelectForm(HTMXWorkflowStep):
    workflow: LibraryAnnotationWorkflow

    template_path = "workflows/library_annotation/sas-project_select.html"

    existing_project = inputs.searchable.SearchableInputField(
        "Select Existing Project",
        route="search_projects",
        required=False,
    )
    new_project = inputs.string.StringInputField(
        "Create New Project",
        max_length=models.Project.title.type.length,
        min_length=6,
        required=False,
    )
    project_description = inputs.string.TextAreaInputField(
        "Project Description",
        max_length=2048,
        required=False,
        description="Describe the project with a few sentences. What samples are in the project? What is the hypothesis? What are the goals of the project?"
    )
    set_requestor_as_owner = inputs.boolean.BooleanInputField(
        "Set the Requestor as Project Owner",
        default=True,
    )

    def __init__(
        self,
        seq_request: models.SeqRequest,
        workflow: LibraryAnnotationWorkflow,
    ) -> None:
        super().__init__(workflow)
        self.seq_request = seq_request

    @property
    def post_url(self) -> responses.URL:
        return ProjectSelectForm.PostURL(ProjectSelectForm.Submit, prefix="LibraryAnnotationWorkflow", seq_request_id=self.seq_request.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            seq_request_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> ProjectSelectForm:
            seq_request = session.get_one(
                Q.seq_request.select(id=seq_request_id).options(
                    orm.joinedload(models.SeqRequest.requestor)
                )
            )
            return cls(seq_request=seq_request, workflow=workflow)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
            form: ProjectSelectForm = Depends(ProjectSelectForm.Init()),
        ) -> Response:
            project_id = workflow.metadata.get("project_id")
            if project_id is not None:
                form.existing_project.data = project_id
            else:
                form.new_project.data = workflow.metadata.get("project_title")
                form.project_description.data = workflow.metadata.get("project_description")
            return form.make_response()
        return route
        

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            form: ProjectSelectForm = Depends(ProjectSelectForm.Validate()),
        ) -> Response:
            project: models.Project | None = None
            if not form.new_project.data and form.existing_project.data is None:
                form.new_project.errors.append("Please select or create a project.")
                form.existing_project.errors.append("Please select or create a project.")
                raise exc.FormValidationException(form)

            if form.existing_project.data is not None:
                project = session.get_one(Q.project.select(id=form.existing_project.data))
                if session.get_access_level(Q.project.permissions(project.id, current_user.id)) < C.AccessLevel.WRITE:
                    form.existing_project.errors.append("You do not have permission to select this project.")
                    raise exc.FormValidationException(form)
                workflow.metadata["project_id"] = project.id
            else:
                if form.new_project.data and not form.project_description.data:
                    form.project_description.errors.append("Please, provide brief description of the project.")
                    raise exc.FormValidationException(form)

                # Existing project does not need a description
                if form.existing_project.data is not None and form.project_description.data:
                    form.project_description.errors.append("Project description is not needed if using existing project.")
                    raise exc.FormValidationException(form)

                if session.exists(Q.project.select(title=form.new_project.data, owner_id=current_user.id)):
                    form.new_project.errors.append("You already have a project with this title.")
                    raise exc.FormValidationException(form)

                workflow.metadata["project_title"] = form.new_project.data
                workflow.metadata["project_description"] = form.project_description.data

            workflow.metadata["seq_request_id"] = form.seq_request.id
            workflow.metadata["user_id"] = current_user.id
            workflow.metadata["project_owner_id"] = (
                form.seq_request.requestor.id
                if form.set_requestor_as_owner.data and current_user.is_insider
                else current_user.id
            )
            workflow.header["submission_type_id"] = form.seq_request.submission_type.id
            next_form = workflow.get_next_step(form)
            return next_form.make_response()
        return route