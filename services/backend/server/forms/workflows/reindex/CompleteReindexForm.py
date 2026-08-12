import pandas as pd
from fastapi import Depends, Response
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ....utils import parsing, barcodes
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow


class CompleteReindexForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/reindex-complete.html"

    def __init__(self, workflow: ReindexWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.barcode_table = self.workflow.tables["barcode_table"]
        self.barcode_table = barcodes.check_indices(self.barcode_table)

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "CompleteReindexForm" = Depends(CompleteReindexForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            # library_table = form.workflow.tables["library_table"]
            barcode_table = form.workflow.tables["barcode_table"]
            tenx_atac_barcode_table = form.workflow.tables.get("tenx_atac_barcode_table")

            barcode_table = barcode_table[barcode_table.get("index_well", pd.Series(dtype=str)) != "del"].copy()

            seq_request_ids: set[int] = set()

            class GroupSchema(BaseModel):
                library_id: int
                index_type: C.IndexType | None

            class RowSchema(BaseModel):
                library_id: int
                kit_i7_id: int | None
                kit_i5_id: int | None
                sequence_i7: str
                sequence_i5: str | None
                name_i7: str | None
                name_i5: str | None
                orientation_i7_id: int | None
                orientation_i5_id: int | None

            for group, _ in parsing.safe_groupby(barcode_table, ["library_id", "index_type"], GroupSchema):
                library = session.get_one(Q.library.select(id=group.library_id))
                seq_request_ids.add(library.seq_request_id)

                library.indices = []
                library.index_type = group.index_type

                if group.index_type == C.IndexType.TENX_ATAC_INDEX:
                    if tenx_atac_barcode_table is None:
                        raise exc.OpeNGSyncServerException("TENX_ATAC_INDEX selected but no ATAC barcode table found.")
                    df = tenx_atac_barcode_table[tenx_atac_barcode_table["library_id"] == group.library_id]
                else:
                    df = barcode_table[barcode_table["library_id"] == group.library_id]

                if df.get("index_well", pd.Series(dtype=str)).eq("del").all():
                    continue

                for _, row in parsing.safe_iter(df, RowSchema):
                    if group.index_type == C.IndexType.TENX_ATAC_INDEX:
                        for _ in range(1, 5):
                            library.indices.append(
                                Q.library_index.create(
                                    library_id=library.id,
                                    index_kit_i7_id=row.kit_i7_id,
                                    sequence_i7=row.sequence_i7,
                                    name_i7=row.name_i7,
                                    name_i5=None,
                                    sequence_i5=None,
                                    index_kit_i5_id=None,
                                    orientation=None
                                )
                            )
                    else:
                        orientation = None
                        if pd.notna(row.orientation_i7_id):
                            orientation = C.BarcodeOrientation.get(int(row.orientation_i7_id))

                        library.indices.append(
                            Q.library_index.create(
                                library_id=library.id,
                                index_kit_i7_id=row.kit_i7_id if pd.notna(row.kit_i7_id) else None,
                                index_kit_i5_id=row.kit_i5_id if pd.notna(row.kit_i5_id) else None,
                                name_i7=row.name_i7 if pd.notna(row.name_i7) else None,
                                name_i5=row.name_i5 if pd.notna(row.name_i5) else None,
                                sequence_i7=row.sequence_i7,
                                sequence_i5=row.sequence_i5 if pd.notna(row.sequence_i5) else None,
                                orientation=orientation,
                            )
                        )

            # Add primer comments if provided
            if (i7_primer := form.workflow.metadata.get("i7_primer")):
                for sr_id in seq_request_ids:
                    session.save(Q.comment.create(
                        text=f"i7 Primer Sequence: {i7_primer}",
                        author=current_user,
                        seq_request_id=sr_id,
                    ))
            if (i5_primer := form.workflow.metadata.get("i5_primer")):
                for sr_id in seq_request_ids:
                    session.save(Q.comment.create(
                        text=f"i5 Primer Sequence: {i5_primer}",
                        author=current_user,
                        seq_request_id=sr_id,
                    ))

            # Redirect
            if form.workflow.seq_request_id is not None:
                redirect = responses.url_for("seq_request_page", seq_request_id=form.workflow.seq_request_id)
            elif form.workflow.lab_prep_id is not None:
                redirect = responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id)
            elif form.workflow.pool_id is not None:
                redirect = responses.url_for("pool_page", pool_id=form.workflow.pool_id)
            else:
                redirect = responses.url_for("dashboard")

            return responses.htmx_response(
                redirect=redirect,
                flash=responses.flash("Libraries Re-Indexed!", "success"),
            )
        return route