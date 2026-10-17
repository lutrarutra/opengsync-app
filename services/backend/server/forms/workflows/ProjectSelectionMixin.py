from opengsync_db import categories as C, models, queries as Q, SyncSession

from ...components import inputs
from ...core import dependencies, exceptions as exc


class ProjectSelectionMixin:
    """Shared existing/new project selection and validation behaviour."""

    project = inputs.searchable.SearchableInputField(
        "Project",
        route="search_projects",
        required=False,
        allow_new=True,
        new_label="Create New Project",
        new_min_length=6,
        new_max_length=models.Project.title.type.length,
        placeholder="Search projects or type the title of a new project…",
    )
    project_description = inputs.string.TextAreaInputField(
        "Project Description",
        max_length=2048,
        # Required for a new project, which is the only case it is shown in (validate_project_selection)
        required=False,
        placeholder="Required: describe the new project in a few sentences (samples, hypothesis, goals).",
        description="Describe the project with a few sentences. What samples are in the project? What is the hypothesis? What are the goals of the project?",
    )

    def validate_project_selection(
        self,
        session: SyncSession,
        current_user: models.User,
        *,
        new_project_owner_id: int | None = None,
        missing_existing_project_is_error: bool = False,
    ) -> models.Project | None:
        """Validate the selection and return an existing project when chosen.

        A ``None`` return value means that a new project should be created by
        the caller using ``new_project_title`` and ``project_description``.
        """
        selection = self.project.data
        if selection is None:
            self.project.errors.append("Please select or create a project.")
            raise exc.FormValidationException(self)

        if isinstance(selection, int):
            if missing_existing_project_is_error:
                project = session.first(Q.project.select(id=selection))
            else:
                project = session.get_one(Q.project.select(id=selection))
            if project is None:
                self.project.errors.append("Selected project not found.")
                raise exc.FormValidationException(self)
            if session.get_access_level(Q.project.permissions(project.id, current_user.id)) < C.AccessLevel.WRITE:
                self.project.errors.append("You do not have permission to select this project.")
                raise exc.FormValidationException(self)
            if self.project_description.data:
                self.project_description.errors.append("Project description is not needed if using existing project.")
                raise exc.FormValidationException(self)
            return project

        if not self.project_description.data:
            self.project_description.errors.append("Please, provide brief description of the project.")
            raise exc.FormValidationException(self)

        owner_id = new_project_owner_id if new_project_owner_id is not None else current_user.id
        if session.exists(Q.project.select(title=selection, owner_id=owner_id)):
            self.project.errors.append("You already have a project with this title.")
            raise exc.FormValidationException(self)

        return None

    @property
    def new_project_title(self) -> str:
        """The title of the new project, once ``validate_project_selection`` returned None."""
        if not isinstance(self.project.data, str):
            raise ValueError("No new project was selected.")
        return self.project.data

    def prefill_project_selection(self, project_id: int | None, title: str | None, description: str | None) -> None:
        """Show the selection made before, e.g. when going back to the step."""
        if project_id is not None:
            self.project.set_selected(project_id, title)
        elif title:
            self.project.set_new(title)
            self.project_description.data = description
