from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession

from ....components import inputs
from ....core import dependencies, exceptions as exc
from ...HTMXForm import FormFunc, RouteFunc, htmx_route
from .SplitProjectWorkflow import SplitProjectWorkflow, SplitProjectWorkflowStep


class SelectSamplesForm(SplitProjectWorkflowStep):
    template_path = "workflows/split_project/select-samples.html"

    selected_sample_ids = inputs.tables.SampleSelectTableField(
        "Samples",
        "split-project",
        required=True,
    )

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: SplitProjectWorkflow = Depends(SplitProjectWorkflow.Init(cls.__name__)),
        ) -> "SelectSamplesForm":
            form = cls(workflow=workflow)
            form.selected_sample_ids.query_params["project_id"] = workflow.project_id
            if "selected_sample_ids" in workflow.metadata:
                form.selected_sample_ids.data = workflow.metadata["selected_sample_ids"]
            return form
        return dependency

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
        ) -> Response:
            selected_ids = form.selected_sample_ids.data
            source_samples = session.get_all(
                Q.sample.select(project_id=form.workflow.project_id)
            )
            source_sample_ids = {sample.id for sample in source_samples}
            invalid_ids = sorted(set(selected_ids) - source_sample_ids)
            if invalid_ids:
                form.selected_sample_ids.data = [sample_id for sample_id in selected_ids if sample_id in source_sample_ids]
                form.add_general_error(
                    "Selected samples do not belong to the source project or no longer exist."
                )
                raise exc.FormValidationException(form)

            form.workflow.metadata["selected_sample_ids"] = selected_ids
            return form.workflow.get_next_step(form).make_response()
        return route
