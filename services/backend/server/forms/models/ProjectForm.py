from typing import Literal
from fastapi import Request, Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, config
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
        form_type: str = "create",
        project: models.Project | None = None,
    ) -> None:
        super().__init__(request)
        self.form_type = form_type
        self.project = project
        if form_type == "create" and project is not None:
            raise exc.OpeNGSyncServerException("Project must be None when form_type is 'create'.")
        if form_type == "edit" and project is None:
            raise exc.OpeNGSyncServerException("Project must be provided when form_type is 'edit'.")

