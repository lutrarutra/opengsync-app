from fastapi import Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...components import inputs
from ...core import dependencies, exceptions as exc, responses
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class AddProjectAssigneeAction(HTMXForm):
    template_path = "actions/add-project-assignee.html"

    user_id = inputs.searchable.SearchableInputField("Select User", route="search_users", required=True)

    def __init__(self, project: models.Project):
        super().__init__()
        self.project = project
        self._context["project"] = project
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", project_id=project.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            project_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ):
            project = session.get_one(Q.project.select(id=project_id), options=[orm.selectinload(models.Project.assignees)])
            return AddProjectAssigneeAction(project=project)
        return form

    @htmx_route("GET", "/add-assignee/{project_id}")
    def Begin(cls) -> RouteFunc:
        def route(
            form: AddProjectAssigneeAction = Depends(AddProjectAssigneeAction.Init()),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            if current_user not in form.project.assignees:
                form.user_id.data = current_user.id
            return form.make_response()
        return route

    @htmx_route("POST", "/add-assignee/{project_id}")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            form: "AddProjectAssigneeAction" = Depends(AddProjectAssigneeAction.Validate()),
            _ = Depends(dependencies.require_insider),
        ):
            assignee = session.get_one(Q.user.select(id=int(form.user_id.data)))

            if not assignee.is_insider:
                form.user_id.errors.append("Only insider users can be assigned to projects.")
                raise exc.FormValidationException(form)

            if assignee in form.project.assignees:
                form.user_id.errors.append(f"User {assignee.name} is already an assignee in this project.")
                raise exc.FormValidationException(form)

            form.project.assignees.append(assignee)
            session.save(form.project)

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=form.project.id).include_query_params(tab="project-assignees-tab"),
                flash=responses.flash("Assignee added successfully.", "success"),
            )
        return route

    @htmx_route("POST", "/assign-me/{project_id}", name="AssignMe")
    def AssignMe(cls) -> RouteFunc:
        def route(
            project_id: int,
            context: str | None = Query(None),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            project = session.get_one(
                Q.project.select(id=project_id),
                options=[orm.selectinload(models.Project.assignees)],
            )

            if current_user in project.assignees:
                raise exc.BadRequestException("User is already an assignee.")

            project.assignees.append(current_user)

            if context == "dashboard":
                return responses.htmx_response(
                    redirect=responses.url_for("dashboard"),
                    flash=responses.flash("Assignee Added!", "success"),
                )

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=project_id),
                flash=responses.flash("Assignee Added!", "success"),
            )
        return route