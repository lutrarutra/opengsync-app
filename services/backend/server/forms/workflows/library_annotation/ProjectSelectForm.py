from fastapi import Request, Depends, Response, APIRouter
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import exceptions as exc, dependencies
from ....components import inputs
from ..HTMXWorkflowStep import HTMXWorkflowStep
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from ...HTMXForm import RouteFunc, FormFunc

class ProjectSelectForm(HTMXWorkflowStep):
    step_name = "project_select"

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
    ) -> None:
        super().__init__()
        self.seq_request = seq_request

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            seq_request_id: int,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> ProjectSelectForm:
            seq_request = session.get_one(
                Q.seq_request.select(id=seq_request_id).options(
                    orm.joinedload(models.SeqRequest.requestor)
                )
            )
            return cls(seq_request=seq_request)
        return dependency

    # def fill_previous_form(self) -> None:
    #     project_id = self.metadata.get("project_id")
    #     if project_id is not None:
    #         self.existing_project.data = project_id
    #     else:
    #         self.new_project.data = self.metadata.get("project_title")
    #         self.project_description.data = self.metadata.get("project_description")

    @classmethod
    def Submit(cls) -> RouteFunc:
        def route(
            request: Request,
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init()),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            form: ProjectSelectForm = Depends(ProjectSelectForm.Init()),
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
                if form.set_requestor_as_owner.data and current_user.is_insider()
                else current_user.id
            )
            next_form = workflow.get_next_step(cls.step_name)
            return next_form.begin(request=request, workflow=workflow)
        return route

    @classmethod
    def Router(cls, prefix: str) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/project-select", cls.Submit(), methods=["POST"], name=f"{prefix}.{cls.__name__}.submit")
        return router