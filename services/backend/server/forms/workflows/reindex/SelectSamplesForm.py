from fastapi import Depends, Response

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep


class SelectSamplesForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/select-samples.html"
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "reindex",
        select_all=True,
        required=False,
    )

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            library_ids = form.selected_library_ids.data
            if not library_ids:
                form.selected_library_ids.errors.append("No libraries selected.")
                raise exc.FormValidationException(form)

            library_table = session.pd.get_lab_prep_libraries(form.workflow.lab_prep_id) if form.workflow.lab_prep_id else session.pd.get_seq_request_libraries(form.workflow.seq_request_id)
            library_table = library_table[library_table["library_id"].isin(library_ids)].copy()

            form.workflow.tables["library_table"] = library_table

            next_step = form.workflow.get_next_step(form)
            return next_step.make_response()
        return route