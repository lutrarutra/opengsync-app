from fastapi import Depends, Response, Query
import pandas as pd
from opengsync_db import categories as C, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc, responses
from ....components import inputs
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .BAReportWorkflow import BAReportWorkflowStep, BAReportWorkflow
from .BAReportForm import BAReportForm

class SelectSamplesForm(BAReportWorkflowStep):
    template_path = "workflows/ba_report/select-samples.html"
    selected_sample_ids = inputs.tables.SampleSelectTableField(
        "Samples",
        "ba-report",
        status_in=[C.SampleStatus.STORED],
        select_all=True,
        required=False
    )
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "ba-report",
        status_in=[C.LibraryStatus.PREPARING],
        select_all=True,
        required=False
    )
    selected_pool_ids = inputs.tables.PoolSelectTableField(
        "Pools",
        "ba-report",
        status_in=[C.PoolStatus.STORED],
        select_all=True,
        required=False
    )
    selected_lane_ids = inputs.tables.LaneSelectTableField(
        "Lanes",
        "ba-report",
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
            workflow: BAReportWorkflow = Depends(BAReportWorkflow.Init(cls.__name__)),
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
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            sample_data = {
                "id": [],
                "name": [],
                "type": [],
                "avg_fragment_size": [],
            }

            for sample in form.selected_sample_ids.get_selected_samples(session):
                sample_data["id"].append(sample.id)
                sample_data["name"].append(sample.name)
                sample_data["avg_fragment_size"].append(sample.avg_fragment_size)
                sample_data["type"].append("sample")


            for library in form.selected_library_ids.get_selected_libraries(session):
                library = session.get_one(Q.library.select(id=library.id))
                sample_data["id"].append(library.id)
                sample_data["name"].append(library.name)
                sample_data["avg_fragment_size"].append(library.avg_fragment_size)
                sample_data["type"].append("library")

            for pool in form.selected_pool_ids.get_selected_pools(session):
                sample_data["id"].append(pool.id)
                sample_data["name"].append(pool.name)
                sample_data["avg_fragment_size"].append(pool.avg_fragment_size)
                sample_data["type"].append("pool")

            for lane in form.selected_lane_ids.get_selected_lanes(session):
                sample_data["id"].append(lane.id)
                sample_data["name"].append(f"{lane.experiment.name} - Lane {lane.number}")
                sample_data["avg_fragment_size"].append(lane.avg_fragment_size)
                sample_data["type"].append("lane")

            sample_table = pd.DataFrame(sample_data)

            if sample_table["name"].duplicated().any():
                form.add_general_error("Duplicate sample names selected.")
                raise exc.FormValidationException(form)

            form.workflow.tables["sample_table"] = sample_table
            form.workflow.add_step(form.__class__.__name__)
            next_form = BAReportForm(workflow=form.workflow)
            return next_form.make_response()
        return route