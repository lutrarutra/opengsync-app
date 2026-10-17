from fastapi import Depends, Response

from opengsync_db import models, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc
from ..ProjectSelectionMixin import ProjectSelectionMixin
from ...HTMXForm import FormFunc, RouteFunc, htmx_route
from .SplitProjectWorkflow import SplitProjectWorkflow, SplitProjectWorkflowStep


class ProjectSelectForm(ProjectSelectionMixin, SplitProjectWorkflowStep):
    template_path = "workflows/split_project/project-select.html"

    def __init__(self, workflow: SplitProjectWorkflow, source_project: models.Project | None = None) -> None:
        super().__init__(workflow)
        self.source_project = source_project

    def prefill_destination(self) -> None:
        self.prefill_project_selection(
            self.workflow.metadata.get("destination_project_id"),
            self.workflow.metadata.get("destination_project_title"),
            self.workflow.metadata.get("destination_project_description"),
        )

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: SplitProjectWorkflow = Depends(SplitProjectWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "ProjectSelectForm":
            source_project = session.first(Q.project.select(id=workflow.project_id))
            form = cls(workflow=workflow, source_project=source_project)
            form.prefill_destination()
            return form
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "ProjectSelectForm" = Depends(ProjectSelectForm.Init()),
        ) -> Response:
            form.prefill_destination()
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            form: "ProjectSelectForm" = Depends(ProjectSelectForm.Validate()),
        ) -> Response:
            source_project = form.source_project or session.first(
                Q.project.select(id=form.workflow.project_id)
            )
            if source_project is None:
                raise exc.NotFoundException("Source project not found.")

            destination_project = form.validate_project_selection(
                session,
                current_user,
                new_project_owner_id=source_project.owner_id,
                missing_existing_project_is_error=True,
            )
            if destination_project is not None:
                if destination_project.id == source_project.id:
                    message = "Source and destination projects cannot be the same."
                    form.project.errors.append(message)
                    raise exc.FormValidationException(form)
                selected_sample_ids = form.workflow.metadata.get("selected_sample_ids", [])
                form.workflow.metadata.clear()
                form.workflow.metadata.update({
                    "selected_sample_ids": selected_sample_ids,
                    "destination_project_id": destination_project.id,
                })
            else:
                selected_sample_ids = form.workflow.metadata.get("selected_sample_ids", [])
                form.workflow.metadata.clear()
                form.workflow.metadata.update({
                    "selected_sample_ids": selected_sample_ids,
                    "destination_project_title": form.new_project_title,
                    "destination_project_description": form.project_description.data,
                })

            return form.workflow.get_next_step(form).make_response()
        return route
