from fastapi import Depends, Response
import pandas as pd

from opengsync_db import SyncSession

from ....core import dependencies
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .RelibWorkflow import RelibWorkflowStep, RelibWorkflow


class SelectSamplesForm(RelibWorkflowStep):
    template_path = "workflows/relib/select-samples.html"
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries", "relib", select_all=True, required=True,
    )

    def __init__(self, workflow: RelibWorkflow) -> None:
        super().__init__(workflow=workflow)
        if self.workflow.seq_request_id is not None:
            self.selected_library_ids.query_params["seq_request_id"] = self.workflow.seq_request_id
        if self.workflow.lab_prep_id is not None:
            self.selected_library_ids.query_params["lab_prep_id"] = self.workflow.lab_prep_id

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Init()),
        ) -> Response:
            library_table = form.workflow.tables["library_table"]
            form.selected_library_ids.data = library_table["library_id"].unique().tolist()
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            library_table_data: dict[str, list] = {
                "library_id": [],
                "sample_name": [],
                "library_name": [],
                "library_type_id": [],
                "service_type_id": [],
                "genome_id": [],
                "nuclei_isolation": [],
            }

            for library in form.selected_library_ids.get_selected_libraries(session):
                library_table_data["library_id"].append(library.id)
                library_table_data["sample_name"].append(library.sample_name)
                library_table_data["library_name"].append(library.name)
                library_table_data["library_type_id"].append(library.type.id)
                library_table_data["service_type_id"].append(library.service_type.id)
                library_table_data["genome_id"].append(library.genome_ref.id)
                library_table_data["nuclei_isolation"].append("Yes" if library.nuclei_isolation else "No")

            form.workflow.tables["library_table"] = pd.DataFrame(library_table_data)
            return form.workflow.get_next_step(form).make_response()
        return route
