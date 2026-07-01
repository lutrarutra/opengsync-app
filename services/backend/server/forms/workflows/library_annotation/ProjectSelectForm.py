from fastapi import Request, Depends, Response
from sqlalchemy import orm

from opengsync_db import models, queries as Q, AsyncSession, categories as C

from ....core import responses, exceptions as exc, dependencies
from ....components import inputs
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow


class ProjectSelectForm(LibraryAnnotationWorkflow):
    _step_name = "project_select"

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
        request: Request,
        seq_request: models.SeqRequest,
        uuid: str | None = None,
    ) -> None:
        super().__init__(
            seq_request=seq_request,
            request=request,
            uuid=uuid,
            step_name=self._step_name,
        )
        self.seq_request = seq_request
        self.post_url = responses.url_for("library_annotation_workflow_select_project", seq_request_id=self.seq_request.id)

    async def fill_previous_form(self) -> None:
        project_id = await self.metadata.get("project_id")
        if project_id is not None:
            self.existing_project.data = project_id
        else:
            self.new_project.data = await self.metadata.get("project_title")
            self.project_description.data = await self.metadata.get("project_description")

    @staticmethod
    async def process_request(
        request: Request,
        seq_request_id: int,
        current_user: models.User = Depends(dependencies.require_user),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id).options(
            orm.joinedload(models.SeqRequest.requestor)
        ))
        form = ProjectSelectForm(request=request, seq_request=seq_request)
        await form._init_msf_state()
        await form.validate()
        await form.metadata.__setitem__("workflow", "library_annotation")

        project: models.Project | None = None
        if not form.new_project.data and form.existing_project.data is None:
            form.new_project.errors.append("Please select or create a project.")
            form.existing_project.errors.append("Please select or create a project.")
            raise exc.FormValidationException(form)

        if form.existing_project.data is not None:
            project = await session.get_one(Q.project.select(id=form.existing_project.data))
            if await session.get_access_level(Q.project.permissions(project.id, current_user.id)) < C.AccessLevel.WRITE:
                form.existing_project.errors.append("You do not have permission to select this project.")
                raise exc.FormValidationException(form)
            await form.metadata.__setitem__("project_id", project.id)
        else:
            if form.new_project.data and not form.project_description.data:
                form.project_description.errors.append("Please, provide brief description of the project.")
                raise exc.FormValidationException(form)

            # Existing project does not need a description
            if form.existing_project.data is not None and form.project_description.data:
                form.project_description.errors.append("Project description is not needed if using existing project.")
                raise exc.FormValidationException(form)

            if await session.exists(Q.project.select(title=form.new_project.data, owner_id=current_user.id)):
                form.new_project.errors.append("You already have a project with this title.")
                raise exc.FormValidationException(form)

            await form.metadata.__setitem__("project_title", form.new_project.data)
            await form.metadata.__setitem__("project_description", form.project_description.data)

        await form.metadata.__setitem__("seq_request_id", form.seq_request.id)
        await form.metadata.__setitem__("user_id", current_user.id)
        await form.metadata.__setitem__(
            "project_owner_id",
            form.seq_request.requestor.id
            if form.set_requestor_as_owner.data and current_user.is_insider()
            else current_user.id,
        )
        next_form = await form.get_next_step()
        return await next_form.begin(previous_form=form)
