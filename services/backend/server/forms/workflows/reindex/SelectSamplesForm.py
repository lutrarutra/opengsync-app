from fastapi import Depends, Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import SyncSession, models, categories as C

from ....core import dependencies, exceptions as exc
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow
from .BarcodeInputForm import BarcodeInputForm

class SelectSamplesForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/select-samples.html"
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries", "reindex", select_all=True, required=True,
    )

    def __init__(self, workflow: ReindexWorkflow) -> None:
        super().__init__(workflow=workflow)
        if self.workflow.seq_request_id is not None:
            self.selected_library_ids.query_params["seq_request_id"] = self.workflow.seq_request_id
        if self.workflow.lab_prep_id is not None:
            self.selected_library_ids.query_params["lab_prep_id"] = self.workflow.lab_prep_id
        if self.workflow.pool_id is not None:
            self.selected_library_ids.query_params["pool_id"] = self.workflow.pool_id

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["library_table"]
            form.selected_library_ids.data = barcode_table["library_id"].unique().tolist()
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            barcode_table_data = {
                "library_id": [],
                "library_name": [],
                "kit_i7": [],
                "kit_i5": [],
                "name_i7": [],
                "name_i5": [],
                "sequence_i7": [],
                "sequence_i5": [],
                "library_type": [],
            }

            library_table_data = {
                "library_id": [],
                "library_name": [],
                "library_type": [],
            }

            for library in form.selected_library_ids.get_selected_libraries(session, options=[
                orm.selectinload(models.Library.indices).selectinload(models.LibraryIndex.index_kit_i7),
                orm.selectinload(models.Library.indices).selectinload(models.LibraryIndex.index_kit_i5),
            ]): 
                library_table_data["library_id"].append(library.id)
                library_table_data["library_name"].append(library.name)
                library_table_data["library_type"].append(library.type)
                for index in library.indices:
                    barcode_table_data["library_id"].append(library.id)
                    barcode_table_data["library_name"].append(library.name)
                    barcode_table_data["kit_i7"].append(index.index_kit_i7.identifier if index.index_kit_i7 else None)
                    barcode_table_data["kit_i5"].append(index.index_kit_i5.identifier if index.index_kit_i5 else None)
                    barcode_table_data["name_i7"].append(index.name_i7)
                    barcode_table_data["name_i5"].append(index.name_i5)
                    barcode_table_data["sequence_i7"].append(index.sequence_i7)
                    barcode_table_data["sequence_i5"].append(index.sequence_i5)
                    barcode_table_data["library_type"].append(library.type)

            df = pd.DataFrame(barcode_table_data)
            form.workflow.tables["library_table"] = pd.DataFrame(library_table_data)
            form.workflow.tables["barcode_table"] = df[df["library_type"] != C.LibraryType.TENX_SC_ATAC].copy()
            form.workflow.tables["tenx_atac_barcode_table"] = df[df["library_type"] == C.LibraryType.TENX_SC_ATAC].copy()
            return form.workflow.get_next_step(form).make_response()
        return route