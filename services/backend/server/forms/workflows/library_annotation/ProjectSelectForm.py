from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, responses
from ....components import inputs
from ..ProjectSelectionMixin import ProjectSelectionMixin
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep
from ...HTMXForm import RouteFunc, FormFunc, htmx_route

class ProjectSelectForm(ProjectSelectionMixin, LibraryAnnotationWorkflowStep):
    template_path = "workflows/library_annotation/sas-project_select.html"

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
            form: ProjectSelectForm = Depends(ProjectSelectForm.Init()),
            _: models.User = Depends(dependencies.require_user),
        ) -> Response:
            project_id = form.workflow.metadata.get("project_id")
            if project_id is not None:
                form.existing_project.data = project_id
            else:
                form.new_project.data = form.workflow.metadata.get("project_title")
                form.project_description.data = form.workflow.metadata.get("project_description")
            return form.make_response()
        return route
        

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            form: ProjectSelectForm = Depends(ProjectSelectForm.Validate()),
        ) -> Response:
            project = form.validate_project_selection(session, current_user)
            if project is not None:
                form.workflow.metadata["project_id"] = project.id
                form.workflow.metadata["project_title"] = project.title
            else:
                form.workflow.metadata["project_title"] = form.new_project.data
                form.workflow.metadata["project_description"] = form.project_description.data

            form.workflow.metadata["seq_request_id"] = form.seq_request.id
            form.workflow.metadata["user_id"] = current_user.id
            form.workflow.metadata["project_owner_id"] = (
                form.seq_request.requestor.id
                if form.set_requestor_as_owner.data and current_user.is_insider
                else current_user.id
            )
            form.workflow.header["submission_type_id"] = form.seq_request.submission_type.id
            form.workflow.header["submitter"] = {
                "id": form.seq_request.requestor.id if form.set_requestor_as_owner.data and current_user.is_insider else current_user.id,
                "name": form.seq_request.requestor.name if form.set_requestor_as_owner.data and current_user.is_insider else current_user.name,
                "email": form.seq_request.requestor.email if form.set_requestor_as_owner.data and current_user.is_insider else current_user.email,
            }

            next_form = form.workflow.get_next_step(form)
            return next_form.make_response()
        return route