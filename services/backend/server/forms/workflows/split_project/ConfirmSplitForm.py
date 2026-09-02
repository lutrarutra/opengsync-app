from fastapi import Depends, Response
from sqlalchemy import orm

from opengsync_db import actions, categories as C, models, queries as Q, SyncSession

from ....components import inputs
from ....core import dependencies, exceptions as exc, responses
from ...HTMXForm import FormFunc, RouteFunc, htmx_route
from .SplitProjectWorkflow import SplitProjectWorkflow, SplitProjectWorkflowStep


class ConfirmSplitForm(SplitProjectWorkflowStep):
    template_path = "workflows/split_project/confirm-split.html"

    destination_status = inputs.selectable.SelectableInputField(
        "Destination Project Status",
        options=C.ProjectStatus.as_selectable(),
        default=C.ProjectStatus.DRAFT.id,
    )

    @property
    def selected_destination_status(self) -> C.ProjectStatus | None:
        try:
            return C.ProjectStatus.get(self.destination_status.data)
        except (TypeError, ValueError):
            return None

    @classmethod
    def build(cls, workflow: SplitProjectWorkflow, session: SyncSession) -> "ConfirmSplitForm":
        return cls(workflow=workflow, session=session)

    def __init__(self, workflow: SplitProjectWorkflow, session: SyncSession) -> None:
        super().__init__(workflow)
        options = [
            orm.selectinload(models.Project.samples).selectinload(models.Sample.library_links),
            orm.selectinload(models.Project.samples).selectinload(models.Sample.plate_links),
        ]

        self.source_project = session.first(
            Q.project.select(id=workflow.project_id),
            options=options,
        )
        selected_ids = workflow.metadata.get("selected_sample_ids", [])
        if self.source_project is None:
            self.selected_samples = []
        else:
            selected_by_id = {sample.id: sample for sample in self.source_project.samples}
            self.selected_samples = [
                selected_by_id[sample_id]
                for sample_id in selected_ids
                if sample_id in selected_by_id
            ]

        destination_project_id = workflow.metadata.get("destination_project_id")
        self.destination_project = None
        if destination_project_id is not None:
            self.destination_project = session.first(
                Q.project.select(id=destination_project_id),
                options=options,
            )

        source_status_id = self.source_project.status_id if self.source_project is not None else C.ProjectStatus.DRAFT.id
        selected_status_id = workflow.metadata.get("destination_status_id", source_status_id)
        self.destination_status.default = selected_status_id
        self.destination_status.data = selected_status_id

        if self.destination_project is not None:
            self.destination_status_original = self.destination_project.status
        else:
            self.destination_status_original = None

        self.destination_is_new = destination_project_id is None
        self.destination_title = (
            self.destination_project.title
            if self.destination_project is not None
            else workflow.metadata.get("destination_project_title")
        )

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: SplitProjectWorkflow = Depends(SplitProjectWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "ConfirmSplitForm":
            return cls(workflow=workflow, session=session)
        return dependency

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "ConfirmSplitForm" = Depends(ConfirmSplitForm.Validate()),
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            source_project = session.first(Q.project.select(id=form.workflow.project_id))
            if source_project is None:
                raise exc.NotFoundException("Source project not found.")

            try:
                destination_status = C.ProjectStatus.get(form.destination_status.data)
            except (TypeError, ValueError):
                form.destination_status.errors.append("Please select a valid destination status.")
                raise exc.FormValidationException(form)

            destination_project = None
            destination_project_id = form.workflow.metadata.get("destination_project_id")
            options = [
                orm.selectinload(models.Project.samples).selectinload(models.Sample.library_links),
                orm.selectinload(models.Project.samples).selectinload(models.Sample.plate_links),
            ]

            if destination_project_id is not None:
                destination_project = session.first(
                    Q.project.select(id=destination_project_id),
                    options=options,
                )
                if destination_project is None:
                    form.add_general_error("The selected destination project no longer exists.")
                    raise exc.FormValidationException(form)
                if destination_project.id == source_project.id:
                    form.add_general_error("Source and destination projects cannot be the same.")
                    raise exc.FormValidationException(form)
                if session.get_access_level(Q.project.permissions(destination_project.id, current_user.id)) < C.AccessLevel.WRITE:
                    form.add_general_error("You do not have permission to select the destination project.")
                    raise exc.FormValidationException(form)
            else:
                title = form.workflow.metadata.get("destination_project_title")
                description = form.workflow.metadata.get("destination_project_description")
                if not title or not description:
                    form.add_general_error("The new destination project is incomplete. Please go back and provide its title and description.")
                    raise exc.FormValidationException(form)
                if session.exists(Q.project.select(title=title, owner_id=source_project.owner_id)):
                    form.add_general_error("A project with the new destination title already exists for the source project owner.")
                    raise exc.FormValidationException(form)
                destination_project = Q.project.create(
                    title=title,
                    description=description,
                    owner_id=source_project.owner_id,
                    group_id=source_project.group_id,
                    status=destination_status,
                )
                session.add(destination_project)
                session.flush()

            assert destination_project is not None
            try:
                form.workflow.metadata["destination_status_id"] = destination_status.id
                destination_project = actions.split_project(
                    session,
                    project_src=source_project,
                    project_dst=destination_project,
                    sample_ids=form.workflow.metadata.get("selected_sample_ids", []),
                    destination_status=destination_status,
                )
            except ValueError as error:
                form.add_general_error(str(error))
                raise exc.FormValidationException(form)

            next_url = responses.url_for("project_page", project_id=destination_project.id)
            form.workflow.complete()
            return responses.htmx_response(
                redirect=next_url,
                flash=responses.flash("Project split successfully!", "success"),
            )
        return route
