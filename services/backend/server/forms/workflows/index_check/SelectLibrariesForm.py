import json

from fastapi import Depends, Response
from sqlalchemy import orm
import pandas as pd

from opengsync_db import SyncSession, models, categories as C

from ....core import dependencies
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .IndexCheckWorkflow import IndexCheckWorkflowStep, IndexCheckWorkflow


def _append_barcode_row(
    data: dict[str, list],
    library: models.Library,
    index: models.LibraryIndex | None = None,
) -> None:
    data["library_id"].append(library.id)
    data["library_name"].append(library.name)
    data["library_type"].append(library.type)
    data["library_index_id"].append(index.id if index else None)
    if index is None:
        data["kit_i7"].append(None)
        data["kit_i5"].append(None)
        data["name_i7"].append(None)
        data["name_i5"].append(None)
        data["sequence_i7"].append(None)
        data["sequence_i5"].append(None)
        data["orientation_i7"].append(None)
        data["orientation_i5"].append(None)
        data["orientation_id"].append(None)
        return
    data["kit_i7"].append(index.index_kit_i7.identifier if index.index_kit_i7 else None)
    data["kit_i5"].append(index.index_kit_i5.identifier if index.index_kit_i5 else None)
    data["name_i7"].append(index.name_i7)
    data["name_i5"].append(index.name_i5)
    data["sequence_i7"].append(index.sequence_i7)
    data["sequence_i5"].append(index.sequence_i5)
    data["orientation_i7"].append(index.orientation)
    data["orientation_i5"].append(index.orientation)
    data["orientation_id"].append(index.orientation.id if index.orientation else None)


def _is_unvalidated_orientation(orientation: C.BarcodeOrientation | None) -> bool:
    return orientation in (
        None,
        C.BarcodeOrientation.FORWARD_NOT_VALIDATED,
        C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED,
    )


class SelectLibrariesForm(IndexCheckWorkflowStep):
    template_path = "workflows/index_check/select-libraries.html"
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries", "index-check", select_all=True, required=True,
    )

    def __init__(self, workflow: IndexCheckWorkflow) -> None:
        super().__init__(workflow=workflow)
        if self.workflow.seq_request_id is not None:
            self.selected_library_ids.query_params["seq_request_id"] = self.workflow.seq_request_id
        if self.workflow.lab_prep_id is not None:
            self.selected_library_ids.query_params["lab_prep_id"] = self.workflow.lab_prep_id
        if self.workflow.pool_id is not None:
            self.selected_library_ids.query_params["pool_id"] = self.workflow.pool_id

        self.selected_library_ids.query_params["barcode_orientation_in"] = json.dumps([
            None,
            C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id,
            C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED.id,
        ])

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectLibrariesForm" = Depends(SelectLibrariesForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectLibrariesForm" = Depends(SelectLibrariesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            barcode_table_data: dict[str, list] = {
                "library_id": [],
                "library_name": [],
                "library_index_id": [],
                "kit_i7": [],
                "kit_i5": [],
                "name_i7": [],
                "name_i5": [],
                "sequence_i7": [],
                "sequence_i5": [],
                "orientation_i7": [],
                "orientation_i5": [],
                "orientation_id": [],
                "library_type": [],
            }

            library_table_data: dict[str, list] = {
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
                if library.indices:
                    for index in library.indices:
                        if _is_unvalidated_orientation(index.orientation):
                            _append_barcode_row(barcode_table_data, library, index)
                else:
                    _append_barcode_row(barcode_table_data, library)

            df = pd.DataFrame(barcode_table_data)
            form.workflow.tables["library_table"] = pd.DataFrame(library_table_data)
            form.workflow.tables["barcode_table"] = df.copy()
            return form.workflow.get_next_step(form).make_response()
        return route