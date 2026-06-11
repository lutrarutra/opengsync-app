from typing import Literal
from fastapi import Request, Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm

class ProjectForm(HTMXForm):
    """Project form handler — validation, rendering, and response logic."""

    template_path = "forms/project.html"

    identifier = inputs.string.StringInputField("Identifier", max_length=models.Project.identifier.type.length, required=False)
    title = inputs.string.StringInputField("Title", max_length=models.Project.title.type.length)
    description = inputs.string.TextAreaInputField("Description", max_length=2048, required=False)
    status = inputs.selectable.SelectableInputField("Status", C.ProjectStatus.as_selectable())
    # owner = inputs.searchable.SearchableInputField("Owner", search_route="search_users", required=True)
    # group = inputs.searchable.OptionalSearchableInputField("Group", search_route="search_groups")
    

    def __init__(
        self,
        request: Request,
        form_type: Literal["create", "edit"],
        project: models.Project | None = None,
    ) -> None:
        super().__init__(request)
        self.form_type = form_type
        self.project = project
        if form_type == "create" and project is not None:
            raise exc.OpeNGSyncServerException("Project must be None when form_type is 'create'.")
        if form_type == "edit" and project is None:
            raise exc.OpeNGSyncServerException("Project must be provided when form_type is 'edit'.")

    @staticmethod
    async def edit_project(
        project_id: int,
        request: Request,
        access_level: C.AccessLevel = Depends(dependencies.project_permissions),
        session: AsyncSession = Depends(dependencies.db_session)
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.PermissionDeniedException("You do not have permission to edit this project.")

        project = await session.get_one(Q.project.select(id=project_id))
        form = ProjectForm(request, form_type="edit", project=project)
        await form.validate()

        if await session.exists(Q.project.select(title=form.title.data, owner_id=project.owner_id).where(models.Project.id != project_id)):
            form.title.errors.append("You already have a project with this title.")
            raise exc.FormValidationException(form)
        
        if await session.exists(Q.project.select(identifier=form.identifier.data).where(models.Project.id != project_id)):
            form.identifier.errors.append("This identifier is already taken.")
            raise exc.FormValidationException(form)
        
        if form.identifier.data and form.identifier.data != project.identifier:
            if access_level < C.AccessLevel.INSIDER:
                form.identifier.errors.append("Only insiders can set a project identifier.")
                raise exc.FormValidationException(form)
            
        if access_level < C.AccessLevel.INSIDER and form.status.data != project.status.id:
            form.status.errors.append("Only insiders can change project status.")
            raise exc.FormValidationException(form)
        
        if access_level < C.AccessLevel.INSIDER and form.user.data != project.owner_id:
            form.user.errors.append("Only insiders can change project owner.")
            raise exc.FormValidationException(form)

        return await responses.htmx_response(
            redirect=request.url_for("project_page", project_id=project.id),
            flash=responses.flash("Project Updated!", "success")
        )