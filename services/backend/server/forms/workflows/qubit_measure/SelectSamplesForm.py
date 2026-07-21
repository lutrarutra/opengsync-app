from fastapi import Depends, Response

from opengsync_db import categories as C

from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .QubitMeasureWorkflow import QubitMeasureWorkflowStep

class SelectSamplesForm(QubitMeasureWorkflowStep):
    template_path = "workflows/qubit-measure/select-samples.html"
    selected_sample_ids = inputs.tables.SampleSelectTableField(
        "Samples",
        "qubit-measure",
        status_in=[C.SampleStatus.STORED],
        select_all=True,
        required=False
    )
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "qubit-measure",
        status_in=[C.LibraryStatus.PREPARING],
        select_all=True,
        required=False
    )
    selected_pool_ids = inputs.tables.PoolSelectTableField(
        "Pools",
        "qubit-measure",
        status_in=[C.PoolStatus.STORED],
        select_all=True,
        required=False
    )
    selected_lane_ids = inputs.tables.LaneSelectTableField(
        "Lanes",
        "qubit-measure",
        select_all=True,
        required=False
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
        ) -> Response:
            form.workflow.metadata["selected_sample_ids"] = form.selected_sample_ids.data
            form.workflow.metadata["selected_library_ids"] = form.selected_library_ids.data
            form.workflow.metadata["selected_pool_ids"] = form.selected_pool_ids.data
            form.workflow.metadata["selected_lane_ids"] = form.selected_lane_ids.data
            return form.workflow.get_next_step(form).make_response()
        return route