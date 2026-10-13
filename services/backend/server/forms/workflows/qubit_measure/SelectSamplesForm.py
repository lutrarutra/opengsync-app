from fastapi import Depends, Response, Query

from opengsync_db import categories as C

from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route, FormFunc
from .QubitMeasureWorkflow import QubitMeasureWorkflowStep, QubitMeasureWorkflow

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


    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: QubitMeasureWorkflow = Depends(QubitMeasureWorkflow.Init(cls.__name__)),
            entity: str | None = Query(None, description="The entity type to select samples for. Can be 'sample', 'library', 'pool', or 'lane'. If not provided, all entity types will be selectable.")
        ) -> "SelectSamplesForm":
            form = cls(workflow=workflow)
            match entity:
                case "sample":
                    form.show_libraries = False
                    form.show_pools = False
                    form.show_lanes = False
                case "library":
                    form.show_samples = False
                    form.show_pools = False
                    form.show_lanes = False
                case "pool":
                    form.show_samples = False
                    form.show_libraries = False
                    form.show_lanes = False
                case "lane":
                    form.show_samples = False
                    form.show_libraries = False
                    form.show_pools = False
                    
            if workflow.lab_prep_id is not None:
                form.selected_sample_ids.query_params["lab_prep_id"] = workflow.lab_prep_id
                form.selected_library_ids.query_params["lab_prep_id"] = workflow.lab_prep_id
                form.selected_lane_ids.query_params["lab_prep_id"] = workflow.lab_prep_id
                form.selected_pool_ids.query_params["lab_prep_id"] = workflow.lab_prep_id
            if workflow.experiment_id is not None:
                form.selected_sample_ids.query_params["experiment_id"] = workflow.experiment_id
                form.selected_library_ids.query_params["experiment_id"] = workflow.experiment_id
                form.selected_lane_ids.query_params["experiment_id"] = workflow.experiment_id
                form.selected_pool_ids.query_params["experiment_id"] = workflow.experiment_id
            return form
        return dependency
    
    
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Validate()),
        ) -> Response:
            if not (form.selected_sample_ids.data or form.selected_library_ids.data or form.selected_pool_ids.data or form.selected_lane_ids.data):
                form.add_general_error("Select at least one sample, library, pool or lane.")
                form.assert_valid()
            form.workflow.metadata["selected_sample_ids"] = form.selected_sample_ids.data
            form.workflow.metadata["selected_library_ids"] = form.selected_library_ids.data
            form.workflow.metadata["selected_pool_ids"] = form.selected_pool_ids.data
            form.workflow.metadata["selected_lane_ids"] = form.selected_lane_ids.data
            return form.workflow.get_next_step(form).make_response()
        return route