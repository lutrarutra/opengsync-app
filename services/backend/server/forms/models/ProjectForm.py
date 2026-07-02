from typing import Literal

from fastapi import Depends, Response, APIRouter

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc


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
    status = inputs.selectable.SelectableInputField("Status", C.ProjectStatus.as_selectable(), default=C.ProjectStatus.DRAFT.id)
    owner = inputs.searchable.SearchableInputField("Owner", route="search_users")
    group = inputs.searchable.SearchableInputField("Group", route="search_groups", required=False)

    def __init__(self, form_type: Literal["create", "edit"], project: models.Project | None) -> None:
        super().__init__()
        self.form_type = form_type
        self.project = project
        if project is None and form_type == "edit":
            raise ValueError("Project must be provided for edit form.")
        elif project is not None and form_type == "create":
            raise ValueError("Project must not be provided for create form.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            project_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "ProjectForm":
            if form_type == "edit" and project_id is None:
                raise exc.OpeNGSyncServerException("Project ID must be provided for edit form.")
            
            project = None
            if project_id is not None:
                project = session.get_one(Q.project.select(id=project_id))
            return cls(form_type=form_type, project=project)
        
        return dependency

    @classmethod
    def Open(
        cls,
        form_type: Literal["create", "edit"],
    ) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_user),
            form: "ProjectForm" = Depends(ProjectForm.Init(form_type=form_type))
        ):
            if form_type == "edit":
                if form.project is None:
                    raise exc.OpeNGSyncServerException("Project ID must be provided for edit form.")
                
                form.identifier.data = form.project.identifier
                form.title.data = form.project.title
                form.description.data = form.project.description
                form.status.data = form.project.status.id
                form.owner.data = form.project.owner_id
                form.group.data = form.project.group_id
            else:
                form.owner.data = current_user.id
            return form.make_response()
        return route

    @classmethod
    def Edit(cls) -> RouteFunc:
        def submit(
            project_id: int,
            access_level: C.AccessLevel = Depends(dependencies.project_permissions),
            session: SyncSession = Depends(dependencies.db_session),
            form: "ProjectForm" = Depends(ProjectForm.Submit(form_type="edit")),
        ) -> Response:
            if form.project is None:
                raise exc.OpeNGSyncServerException("Project ID must be provided for edit form.")
            
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this project.")

            if session.exists(
                Q.project.select(title=form.title.data, owner_id=form.project.owner_id).where(
                    models.Project.id != project_id
                )
            ):
                form.title.errors.append("You already have a project with this title.")
                raise exc.FormValidationException(form)

            if form.identifier.data and session.exists(
                Q.project.select(identifier=form.identifier.data).where(models.Project.id != project_id)
            ):
                form.identifier.errors.append("This identifier is already taken.")
                raise exc.FormValidationException(form)

            if form.identifier.data and form.identifier.data != form.project.identifier:
                if access_level < C.AccessLevel.INSIDER:
                    form.identifier.errors.append("Only insiders can set a project identifier.")
                    raise exc.FormValidationException(form)

            if (
                access_level < C.AccessLevel.INSIDER
                and form.status.data != form.project.status.id
            ):
                form.status.errors.append("Only insiders can change project status.")
                raise exc.FormValidationException(form)

            if access_level < C.AccessLevel.INSIDER and form.owner.data != form.project.owner_id:
                form.owner.errors.append("Only insiders can change project owner.")
                raise exc.FormValidationException(form)

            form.project.identifier = form.identifier.data
            form.project.title = form.title.data
            form.project.description = form.description.data
            form.project.status_id = form.status.data
            form.project.owner_id = form.owner.data
            form.project.group_id = form.group.data

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=form.project.id),
                flash=responses.flash("Project Updated!", "success"),
            )
        return submit

    @classmethod
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),                
            form: "ProjectForm" = Depends(ProjectForm.Submit(form_type="create")),
        ) -> Response:
            if session.exists(
                Q.project.select(title=form.title.data, owner_id=form.owner.data)
            ):
                form.title.errors.append("You already have a project with this title.")
                raise exc.FormValidationException(form)

            if session.exists(Q.project.select(identifier=form.identifier.data)):
                form.identifier.errors.append("This identifier is already taken.")
                raise exc.FormValidationException(form)

            if form.identifier.data and not current_user.is_insider():
                form.identifier.errors.append("Only insiders can set a project identifier.")
                raise exc.FormValidationException(form)

            project = session.save(Q.project.create(
                identifier=form.identifier.data,
                title=form.title.data,
                description=form.description.data,
                status=C.ProjectStatus.get(form.status.data),
                owner_id=form.owner.data,
            ), flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=project.id),
                flash=responses.flash("Project Created!", "success"),
            )
        return submit
    
    @classmethod
    def Router(cls) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/create", cls.Open(form_type="create"),           methods=["GET"], name="ProjectForm.create")
        router.add_api_route("/create", cls.Create(),                           methods=["POST"], name="ProjectForm.create")
        router.add_api_route("/{project_id}/edit", cls.Open(form_type="edit"),  methods=["GET"], name="ProjectForm.edit")
        router.add_api_route("/{project_id}/edit", cls.Edit(),                  methods=["POST"], name="ProjectForm.edit")
        return router