from opengsync_db import categories as C, models, queries as Q, SyncSession

from ...components import inputs
from ...core import dependencies, exceptions as exc


class ProjectSelectionMixin:
    """Shared existing/new project selection and validation behaviour."""

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
        the caller using ``new_project`` and ``project_description``.
        """
        if not self.new_project.data and self.existing_project.data is None:
            self.new_project.errors.append("Please select or create a project.")
            self.existing_project.errors.append("Please select or create a project.")
            raise exc.FormValidationException(self)

        if self.existing_project.data is not None:
            if missing_existing_project_is_error:
                project = session.first(Q.project.select(id=self.existing_project.data))
            else:
                project = session.get_one(Q.project.select(id=self.existing_project.data))
            if project is None:
                self.existing_project.errors.append("Selected project not found.")
                raise exc.FormValidationException(self)
            if session.get_access_level(Q.project.permissions(project.id, current_user.id)) < C.AccessLevel.WRITE:
                self.existing_project.errors.append("You do not have permission to select this project.")
                raise exc.FormValidationException(self)
            if self.project_description.data:
                self.project_description.errors.append("Project description is not needed if using existing project.")
                raise exc.FormValidationException(self)
            return project

        if not self.project_description.data:
            self.project_description.errors.append("Please, provide brief description of the project.")
            raise exc.FormValidationException(self)

        owner_id = new_project_owner_id if new_project_owner_id is not None else current_user.id
        if session.exists(Q.project.select(title=self.new_project.data, owner_id=owner_id)):
            self.new_project.errors.append("You already have a project with this title.")
            raise exc.FormValidationException(self)

        return None
