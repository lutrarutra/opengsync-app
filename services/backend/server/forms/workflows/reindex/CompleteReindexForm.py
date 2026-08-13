import pandas as pd
from fastapi import Depends, Response
from loguru import logger
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
        if "index_well" in self.barcode_table.columns:
            self.barcode_table = self.barcode_table.loc[(self.barcode_table["index_well"] != "del") | (self.barcode_table["index_well"].isna())].copy()
        if "orientation_i7_id" in self.barcode_table.columns:
            self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
        self.barcode_table = barcodes.check_indices(self.barcode_table)

        tenx_atac_barcode_table = self.workflow.tables.get("tenx_atac_barcode_table")
        if tenx_atac_barcode_table is not None and not tenx_atac_barcode_table.empty:
            display_atac = tenx_atac_barcode_table
            if "index_well" in display_atac.columns:
                display_atac = display_atac.loc[
                    (display_atac["index_well"] != "del") | display_atac["index_well"].isna()
                ].copy()
            self.barcode_table = pd.concat([self.barcode_table, display_atac], ignore_index=True)

        if (
            "orientation_i7_id" in self.barcode_table.columns
            and "orientation_i5_id" in self.barcode_table.columns
            and "orientation_id" in self.barcode_table.columns
        ):
            self.barcode_table.loc[
                pd.notna(self.barcode_table["orientation_i7_id"])
                & (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
                "orientation_id",
            ] = None

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "CompleteReindexForm" = Depends(CompleteReindexForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "CompleteReindexForm" = Depends(CompleteReindexForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            library_table = form.workflow.tables["library_table"].copy()
            barcode_table = form.workflow.tables["barcode_table"]
            tenx_atac_barcode_table = form.workflow.tables.get("tenx_atac_barcode_table")

            library_table["index_type_id"] = None
            if not barcode_table.empty and "index_type_id" in barcode_table.columns:
                for _, row in barcode_table.iterrows():
                    library_table.loc[
                        library_table["library_id"] == row["library_id"],
                        "index_type_id",
                    ] = row["index_type_id"]
            if tenx_atac_barcode_table is not None and not tenx_atac_barcode_table.empty:
                atac_type_id = C.IndexType.TENX_ATAC_INDEX.id
                for _, row in tenx_atac_barcode_table.iterrows():
                    library_table.loc[
                        library_table["library_id"] == row["library_id"],
                        "index_type_id",
                    ] = row["index_type_id"] if "index_type_id" in tenx_atac_barcode_table.columns else atac_type_id

            class LibrarySchema(BaseModel):
                library_id: int
                index_type_id: int | None

            class BarcodeRowSchema(BaseModel):
                library_id: int
                kit_i7_id: int | None = None
                kit_i5_id: int | None = None
                sequence_i7: str
                sequence_i5: str | None = None
                name_i7: str | None = None
                name_i5: str | None = None
                orientation_i7_id: int | None = None
                orientation_i5_id: int | None = None
                index_well: str | None = None

            class AtacRowSchema(BaseModel):
                library_id: int
                library_name: str | None = None
                kit_id: int | None = None
                name: str | None = None
                sequence_1: str | None = None
                sequence_2: str | None = None
                sequence_3: str | None = None
                sequence_4: str | None = None
                index_well: str | None = None

            seq_request_ids: set[int] = set()

            for _, library_row in parsing.safe_iter(library_table, LibrarySchema):
                library = session.get_one(Q.library.select(id=library_row.library_id))
                seq_request_ids.add(library.seq_request_id)

                if library_row.index_type_id is None:
                    index_type = None
                else:
                    try:
                        index_type = C.IndexType.get(int(library_row.index_type_id))
                    except ValueError:
                        logger.error(f"{form.workflow.uuid}: Invalid index_type_id {library_row.index_type_id} for library {library_row.library_id}")
                        raise exc.OpeNGSyncServerException(f"Invalid index type for library {library.name}.")

                library.indices = []
                library.index_type = index_type

                if index_type == C.IndexType.TENX_ATAC_INDEX:
                    if tenx_atac_barcode_table is None:
                        raise exc.OpeNGSyncServerException("TENX_ATAC_INDEX selected but no ATAC barcode table found.")
                    df = tenx_atac_barcode_table.loc[
                        tenx_atac_barcode_table["library_id"] == library_row.library_id,
                        :,
                    ].copy()
                else:
                    df = barcode_table.loc[barcode_table["library_id"] == library_row.library_id, :].copy()

                if "index_well" in df.columns:
                    keep = (df["index_well"] != "del") | df["index_well"].isna()
                    if not bool(keep.any()):
                        continue
                    df = df.loc[keep].copy()

                if index_type == C.IndexType.TENX_ATAC_INDEX:
                    if len(df) != 1:
                        logger.warning(
                            f"{form.workflow.uuid}: Expected 1 TENX ATAC barcode row for {library.name}, found {len(df)}."
                        )
                    for _, row in parsing.safe_iter(df, AtacRowSchema):
                        if row.index_well == "del":
                            continue
                        for i in range(1, 5):
                            sequence = getattr(row, f"sequence_{i}")
                            if sequence is None:
                                logger.error(
                                    f"{form.workflow.uuid}: Missing sequence_{i} for TENX_ATAC_INDEX in library {row.library_name}."
                                )
                                raise exc.OpeNGSyncServerException(
                                    f"Missing sequence_{i} for TENX_ATAC_INDEX in library {row.library_name}."
                                )
                            library.indices.append(
                                Q.library_index.create(
                                    library_id=library.id,
                                    index_kit_i7_id=row.kit_id,
                                    index_kit_i5_id=None,
                                    name_i7=row.name,
                                    name_i5=None,
                                    sequence_i7=sequence,
                                    sequence_i5=None,
                                    orientation=C.BarcodeOrientation.FORWARD if row.kit_id is not None else None,
                                )
                            )
                else:
                    if len(df) != 1:
                        logger.warning(
                            f"{form.workflow.uuid}: Expected 1 barcode for index type {index_type}, found {len(df)}."
                        )
                    for _, row in parsing.safe_iter(df, BarcodeRowSchema):
                        if row.index_well == "del":
                            continue
                        orientation = None
                        if row.orientation_i7_id is not None:
                            orientation = C.BarcodeOrientation.get(int(row.orientation_i7_id))
                        if (
                            orientation is not None
                            and row.orientation_i5_id is not None
                            and orientation.id != row.orientation_i5_id
                        ):
                            logger.error(
                                f"{form.workflow.uuid}: Conflicting orientations for i7 and i5 in library {library.name}."
                            )
                            raise exc.OpeNGSyncServerException("Conflicting orientations for i7 and i5.")
                        library.indices.append(
                            Q.library_index.create(
                                library_id=library.id,
                                index_kit_i7_id=row.kit_i7_id,
                                index_kit_i5_id=row.kit_i5_id,
                                name_i7=row.name_i7,
                                name_i5=row.name_i5,
                                sequence_i7=row.sequence_i7,
                                sequence_i5=row.sequence_i5,
                                orientation=orientation,
                            )
                        )

            match_form = form.workflow.metadata.get("barcode_match_form", {})
            i7_primer = match_form.get("i7_primer") or form.workflow.metadata.get("i7_primer")
            i5_primer = match_form.get("i5_primer") or form.workflow.metadata.get("i5_primer")
            if i7_primer:
                for sr_id in seq_request_ids:
                    session.save(Q.comment.create(
                        text=f"i7 Primer Sequence: {i7_primer}",
                        author=current_user,
                        seq_request_id=sr_id,
                    ))
            if i5_primer:
                for sr_id in seq_request_ids:
                    session.save(Q.comment.create(
                        text=f"i5 Primer Sequence: {i5_primer}",
                        author=current_user,
                        seq_request_id=sr_id,
                    ))

            form.workflow.complete()

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
