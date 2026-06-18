from typing import Literal
from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm


class ProjectForm(HTMXForm):
    template_path = "forms/project.html"

    identifier = inputs.string.StringInputField(
        "Identifier",
        max_length=models.Project.identifier.type.length,
        required=False,
        placeholder="BSA_XXXX",
    )
    title = inputs.string.StringInputField("Title", max_length=models.Project.title.type.length)
    description = inputs.string.TextAreaInputField("Description", max_length=2048, required=False)
    status = inputs.selectable.SelectableInputField("Status", C.ProjectStatus.as_selectable())
    owner = inputs.searchable.SearchableInputField("Owner", route="search_users")
    group = inputs.searchable.SearchableInputField("Group", route="search_groups", required=False)

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
            raise exc.OpeNGSyncServerException(
                "Project must be None when form_type is 'create'."
            )
        if form_type == "edit" and project is None:
            raise exc.OpeNGSyncServerException(
                "Project must be provided when form_type is 'edit'."
            )

    async def prepare(self):
        if self.form_type == "edit" and self.project is not None:
            self.identifier.data = self.project.identifier
            self.title.data = self.project.title
            self.description.data = self.project.description
            self.status.data = self.project.status.id
            self.owner.data = self.project.owner_id
            self.group.data = self.project.group_id
        if self.form_type == "create":
            self.status.data = C.ProjectStatus.DRAFT.id
            self.owner.data = self.request.state.current_user.id

    @staticmethod
    async def edit_project(
        project_id: int,
        request: Request,
        access_level: C.AccessLevel = Depends(dependencies.project_permissions),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.NoPermissionsException("You do not have permission to edit this project.")

        project = await session.get_one(Q.project.select(id=project_id))
        form = ProjectForm(request, form_type="edit", project=project)
        await form.validate()

        if await session.exists(
            Q.project.select(title=form.title.data, owner_id=project.owner_id).where(
                models.Project.id != project_id
            )
        ):
            form.title.errors.append("You already have a project with this title.")
            raise exc.FormValidationException(form)

        if await session.exists(
            Q.project.select(identifier=form.identifier.data).where(
                models.Project.id != project_id
            )
        ):
            form.identifier.errors.append("This identifier is already taken.")
            raise exc.FormValidationException(form)

        if form.identifier.data and form.identifier.data != project.identifier:
            if access_level < C.AccessLevel.INSIDER:
                form.identifier.errors.append(
                    "Only insiders can set a project identifier."
                )
                raise exc.FormValidationException(form)

        if (
            access_level < C.AccessLevel.INSIDER
            and form.status.data != project.status.id
        ):
            form.status.errors.append("Only insiders can change project status.")
            raise exc.FormValidationException(form)

        if access_level < C.AccessLevel.INSIDER and form.owner.data != project.owner_id:
            form.owner.errors.append("Only insiders can change project owner.")
            raise exc.FormValidationException(form)

        project.identifier = form.identifier.data
        project.title = form.title.data
        project.description = form.description.data
        project.status_id = form.status.data
        project.owner_id = form.owner.data
        project.group_id = form.group.data

        return await responses.htmx_response(
            redirect=request.url_for("project_page", project_id=project.id),
            flash=responses.flash("Project Updated!", "success"),
        )

    @staticmethod
    async def create_project(
        request: Request,
        access_level: C.AccessLevel = Depends(dependencies.project_permissions),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.NoPermissionsException(
                "You do not have permission to create a project."
            )

        form = ProjectForm(request, form_type="create")
        from loguru import logger
        logger.debug(await request.form())
        await form.validate()

        if await session.exists(
            Q.project.select(title=form.title.data, owner_id=form.owner.data)
        ):
            form.title.errors.append("You already have a project with this title.")
            raise exc.FormValidationException(form)

        if await session.exists(Q.project.select(identifier=form.identifier.data)):
            form.identifier.errors.append("This identifier is already taken.")
            raise exc.FormValidationException(form)

        if form.identifier.data and access_level < C.AccessLevel.INSIDER:
            form.identifier.errors.append(
                "Only insiders can set a project identifier."
            )
            raise exc.FormValidationException(form)

        project = await session.save(Q.project.create(
            identifier=form.identifier.data,
            title=form.title.data,
            description=form.description.data,
            status=C.ProjectStatus.get(form.status.data),
            owner_id=form.owner.data,
        ), flush=True)

        return await responses.htmx_response(
            redirect=request.url_for("project_page", project_id=project.id),
            flash=responses.flash("Project Created!", "success"),
        )