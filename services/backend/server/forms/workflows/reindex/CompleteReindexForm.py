import pandas as pd
from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, exceptions as exc, responses
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep


class CompleteReindexForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/reindex-complete.html"

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "CompleteReindexForm" = Depends(CompleteReindexForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            library_table = form.workflow.tables.get("library_table")
            barcode_table = form.workflow.tables.get("barcode_table")
            tenx_atac_barcode_table = form.workflow.tables.get("tenx_atac_barcode_table")

            if library_table is None or barcode_table is None:
                raise exc.OpeNGSyncServerException("Missing required workflow data.")

            barcode_table = barcode_table[barcode_table.get("index_well", pd.Series(dtype=str)) != "del"].copy()

            seq_request_ids: set[int] = set()

            for (library_id, index_type_id), group in library_table.groupby(["library_id", "index_type_id"], dropna=False, sort=False):
                library = session.get_one(Q.library.select(id=int(library_id)))
                seq_request_ids.add(library.seq_request_id)

                try:
                    if pd.notna(index_type_id):
                        index_type = C.IndexType.get(int(index_type_id))
                    else:
                        index_type = C.IndexType.DUAL_INDEX
                except (ValueError, TypeError):
                    index_type = C.IndexType.DUAL_INDEX

                library.indices = []
                library.index_type = index_type

                if index_type == C.IndexType.TENX_ATAC_INDEX:
                    if tenx_atac_barcode_table is None:
                        raise exc.OpeNGSyncServerException("TENX_ATAC_INDEX selected but no ATAC barcode table found.")
                    df = tenx_atac_barcode_table[tenx_atac_barcode_table["library_id"] == int(library_id)]
                else:
                    df = barcode_table[barcode_table["library_id"] == int(library_id)]

                if df.get("index_well", pd.Series(dtype=str)).eq("del").all():
                    continue

                for _, row in df.iterrows():
                    if index_type == C.IndexType.TENX_ATAC_INDEX:
                        for i in range(1, 5):
                            library.indices.append(
                                Q.library_index.create(
                                    library_id=library.id,
                                    index_kit_i7_id=int(row.get("kit_id")) if pd.notna(row.get("kit_id")) else None,
                                    sequence_i7=row[f"sequence_{i}"],
                                    name_i7=row.get("name") if pd.notna(row.get("name")) else None,
                                )
                            )
                    else:
                        orientation = None
                        if pd.notna(row.get("orientation_i7_id")):
                            orientation = C.BarcodeOrientation.get(int(row["orientation_i7_id"]))

                        library.indices.append(
                            Q.library_index.create(
                                library_id=library.id,
                                index_kit_i7_id=int(row["kit_i7_id"]) if pd.notna(row.get("kit_i7_id")) else None,
                                index_kit_i5_id=int(row["kit_i5_id"]) if pd.notna(row.get("kit_i5_id")) else None,
                                name_i7=row.get("name_i7") if pd.notna(row.get("name_i7")) else None,
                                name_i5=row.get("name_i5") if pd.notna(row.get("name_i5")) else None,
                                sequence_i7=row["sequence_i7"],
                                sequence_i5=row.get("sequence_i5") if pd.notna(row.get("sequence_i5")) else None,
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